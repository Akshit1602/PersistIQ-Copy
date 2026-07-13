"""Continum LLM client (OpenAI/Azure) + credentials + lifecycle manager (merged)."""

from __future__ import annotations

# ===== merged from core/llm/config.py =====
"""
LLM credential loading + provider detection for Continum.

Single source of truth used by both ``core.llm.client`` (the app-wide LLM client)
and ``runtime.ask.askdata.llm`` (the AskData LangGraph engine). Credentials may be
supplied via real environment variables, a repo-root ``.env`` (python-dotenv), or a
``.streamlit/secrets.toml`` (kept for parity with the AskData docs). Real env vars
always win; we only fill gaps.
"""

import os
import threading
from pathlib import Path

_LOCK = threading.Lock()
_LOADED = False


def _repo_root() -> Path:
    # Repo root = the parent of the 'continum' package — found by walking up so it
    # stays correct regardless of where this module lives inside the package.
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "continum":
            return parent.parent
    return here.parents[2]


def load_credentials() -> None:
    """Populate os.environ from .env and/or .streamlit/secrets.toml (once)."""
    global _LOADED
    if _LOADED:
        return
    with _LOCK:
        if _LOADED:
            return
        root = _repo_root()
        try:
            from dotenv import load_dotenv

            p = root / ".env"
            if p.exists():
                load_dotenv(p, override=False)
        except Exception:
            pass
        try:
            import tomllib  # Python 3.11+

            p = root / ".streamlit" / "secrets.toml"
            if p.exists():
                with open(p, "rb") as fh:
                    data = tomllib.load(fh)
                for k, v in data.items():
                    if isinstance(v, str):
                        os.environ.setdefault(k, v)
        except Exception:
            pass
        _LOADED = True


def active_provider() -> str:
    """Return the LLM backend to use: 'azure' | 'openai' | 'unconfigured'."""
    load_credentials()
    if (
        os.getenv("OPENAI_API_TYPE", "").lower() == "azure"
        and os.getenv("OPENAI_API_KEY")
        and (os.getenv("OPENAI_API_BASE") or os.getenv("AZURE_OPENAI_ENDPOINT"))
        and (os.getenv("OPENAI_DEPLOYMENT_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT"))
    ):
        return "azure"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "unconfigured"


def is_configured() -> bool:
    return active_provider() != "unconfigured"


def openai_model() -> str:
    load_credentials()
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


__all__ = ["load_credentials", "active_provider", "is_configured", "openai_model"]

# ===== merged from core/llm/client.py =====
"""
Continum LLM client — OpenAI-backed.

Previously this wrapped a local Qwen2.5 transformers model. It now talks to
OpenAI (or Azure OpenAI) via ``langchain_openai`` while preserving the exact
public surface the rest of the app depends on:

    ask(prompt, system="")        -> str
    narrate(data, context)        -> str
    ask_grounded(question, ...)   -> str
    _load()                       -> None        (no-op-ish; builds the chat model)
    unload()                      -> None
    is_loaded                     -> bool        (True when credentials are configured)
    status()                      -> dict

``TransformersClient`` is kept as a backward-compatible alias of :class:`LLMClient`
so ``core.llm.manager`` and ``core.llm.__init__`` import unchanged.

Configure with ``OPENAI_API_KEY`` (+ optional ``OPENAI_MODEL``) in a repo-root
``.env`` or ``.streamlit/secrets.toml`` — see ``core.llm.config``.
"""

import json
import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger("continum.crosscutting.llm")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

AGENT_CONFIG: Dict[str, Any] = {
    "model_id": "gpt-4o-mini",  # default; overridden by OPENAI_MODEL env
    "max_new_tokens": 2048,
    "temperature": 0.3,
}

# Grounding system prompt — ensures the model ONLY uses provided data
GROUNDING_SYSTEM = (
    "You are a senior data scientist presenting findings to VPs and heads of department. "
    "Your responses MUST be grounded exclusively in the data and numbers provided in the prompt. "
    "Do NOT invent, extrapolate, or assume any numbers not explicitly stated. "
    "If data is insufficient to answer, say so clearly. "
    "Write clear, concise, executive-level insights with specific numbers. "
    "Flag risks and opportunities. Be direct — no filler phrases. "
    "Write in plain business language. Do not use emojis, icons, or decorative symbols."
)

_NOT_CONFIGURED = "[LLM not configured — set OPENAI_API_KEY in .streamlit/secrets.toml or .env]"


# ─────────────────────────────────────────────────────────────────────────────
# OPENAI CLIENT
# ─────────────────────────────────────────────────────────────────────────────


class LLMClient:
    """OpenAI / Azure OpenAI chat client with Continum's historical method surface."""

    def __init__(self, config: Optional[Dict] = None):
        load_credentials()
        cfg = config or AGENT_CONFIG
        self.max_new_tokens = cfg.get("max_new_tokens", 2048)
        self.temperature = cfg.get("temperature", 0.3)
        self.provider = active_provider()
        if self.provider == "azure":
            self.model_id = (
                os.getenv("OPENAI_DEPLOYMENT_NAME")
                or os.getenv("AZURE_OPENAI_DEPLOYMENT")
                or "gpt-4o"
            )
        else:
            self.model_id = openai_model()
        self._chat = None
        self._load_lock = threading.Lock()
        logger.info("LLMClient configured: provider=%s model=%s", self.provider, self.model_id)

    # ── Lazy chat-model builder ───────────────────────────────────────────────

    def _build_chat(self):
        prov = active_provider()
        if prov == "azure":
            from langchain_openai import AzureChatOpenAI

            return AzureChatOpenAI(
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                azure_endpoint=os.getenv("OPENAI_API_BASE") or os.getenv("AZURE_OPENAI_ENDPOINT"),
                deployment_name=os.getenv("OPENAI_DEPLOYMENT_NAME")
                or os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                openai_api_version=os.getenv("OPENAI_API_VERSION", "2024-05-01-preview"),
                temperature=self.temperature,
                max_tokens=self.max_new_tokens,
            )
        if prov == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=self.model_id,
                temperature=self.temperature,
                max_tokens=self.max_new_tokens,
            )
        return None

    def _load(self) -> None:
        """Build the chat model. Cheap — no network call until first ask()."""
        if self._chat is not None:
            return
        with self._load_lock:
            if self._chat is None:
                self._chat = self._build_chat()

    # ── Core chat method ───────────────────────────────────────────────────────

    def ask(self, prompt: str, system: str = "") -> str:
        self._load()
        if self._chat is None:
            return _NOT_CONFIGURED
        try:
            messages = [
                ("system", system or GROUNDING_SYSTEM),
                ("human", prompt),
            ]
            resp = self._chat.invoke(messages)
            return str(getattr(resp, "content", resp)).strip()
        except Exception as e:
            logger.error("LLMClient.ask() error: %s", e)
            return f"[LLM error: {e}]"

    # ── Narrative helper ───────────────────────────────────────────────────────

    def narrate(self, data: Any, context: str) -> str:
        data_str = json.dumps(data, indent=2, default=str)
        if len(data_str) > 6000:
            data_str = data_str[:6000] + "\n... [truncated]"
        prompt = f"{context}\n\nData:\n{data_str}"
        return self.ask(prompt)

    # ── Grounded Ask helper ────────────────────────────────────────────────────

    def ask_grounded(
        self,
        question: str,
        session_context: str,
        reasoning_chain: Optional[str] = None,
        historical_context: str = "",
    ) -> str:
        context_parts = ["=== SESSION CONTEXT ===", session_context]
        if reasoning_chain:
            context_parts += ["", "=== EVIDENCE CHAIN ===", reasoning_chain]
        if historical_context:
            context_parts += ["", "=== HISTORICAL PATTERNS ===", historical_context]

        context_block = "\n".join(context_parts)
        if len(context_block) > 8000:
            context_block = context_block[:8000] + "\n... [context truncated]"

        prompt = (
            f"{context_block}\n\n"
            f"=== QUESTION ===\n{question}\n\n"
            f"Answer ONLY using the data above. "
            f"If the data doesn't contain enough to answer, say so explicitly. "
            f"Be specific with numbers. Be direct."
        )
        system = (
            "You are a senior experimentation analyst. "
            "You answer questions about A/B experiments based exclusively on the "
            "session data provided. Do not invent numbers or make assumptions "
            "beyond what the data shows. "
            "If results are inconclusive, say so. "
            "Use plain business language."
        )
        return self.ask(prompt, system=system)

    # ── Lifecycle / status ─────────────────────────────────────────────────────

    def unload(self) -> None:
        self._chat = None

    @property
    def is_loaded(self) -> bool:
        return is_configured()

    def status(self) -> Dict:
        return {
            "model_id": self.model_id,
            "is_loaded": self.is_loaded,
            "device": self.provider,  # 'openai' | 'azure' | 'unconfigured'
            "provider": self.provider,
            "max_new_tokens": self.max_new_tokens,
        }


# Backward-compatible alias — the rest of the codebase historically imported
# ``TransformersClient`` (now OpenAI-backed).
TransformersClient = LLMClient


__all__ = ["LLMClient", "TransformersClient", "AGENT_CONFIG", "GROUNDING_SYSTEM"]

# ===== merged from core/llm/manager.py =====
import logging
import threading

logger = logging.getLogger("continum.crosscutting.llm")

_INSTANCE: Optional["TransformersClient"] = None  # type: ignore
_MGR_LOCK = (
    threading.Lock()
)  # distinct from the credentials _LOCK above (merge: avoid re-entrant deadlock)


def get_llm():
    return _INSTANCE


def require_llm(config=None):
    global _INSTANCE
    if _INSTANCE is None:
        with _MGR_LOCK:
            if _INSTANCE is None:
                _INSTANCE = TransformersClient(config or AGENT_CONFIG)
                logger.info("TransformersClient created (model not yet loaded)")
    return _INSTANCE


def load_llm(config=None):
    llm = require_llm(config)
    llm._load()
    return llm


def unload_llm():
    if _INSTANCE is not None:
        _INSTANCE.unload()


def llm_status() -> dict:
    if _INSTANCE is None:
        return {
            "available": False,
            "is_loaded": False,
            "model_id": None,
            "device": None,
            "max_new_tokens": 0,
            "message": "LLM not initialised. Call /api/llm/load to start.",
        }
    s = _INSTANCE.status()
    s["available"] = True
    s["message"] = (
        f"Model loaded on {s['device']}."
        if s["is_loaded"]
        else "Model not loaded — will load on first use."
    )
    return s


__all__ = [
    "get_llm",
    "require_llm",
    "load_llm",
    "unload_llm",
    "llm_status",
]
