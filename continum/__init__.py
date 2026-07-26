"""Continum — experimentation intelligence platform.

This package root is also the **single LLM initialisation point** for the whole
project. Credentials come from real environment variables or a repo-root
``.env`` (python-dotenv) — and nothing else. There is exactly one secrets source.

Public surface used across the codebase::

    active_provider() / is_configured() / openai_model() / load_credentials()
    get_chat_llm()                # LangChain chat model for LangGraph nodes
    LLMClient                     # historical .ask/.narrate/.ask_grounded client
    get_llm / require_llm / load_llm / unload_llm / llm_status   # lifecycle manager
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

__version__ = "1.0.0"

logger = logging.getLogger("continum.llm")

# ─────────────────────────────────────────────────────────────────────────────
# CREDENTIALS  (.env only)
# ─────────────────────────────────────────────────────────────────────────────

_CRED_LOCK = threading.Lock()
_CRED_LOADED = False


def _repo_root() -> Path:
    """Repo root = the parent of the ``continum`` package (this file lives in it)."""
    return Path(__file__).resolve().parent.parent


def load_credentials() -> None:
    """Populate ``os.environ`` from a repo-root ``.env`` (once). Real env vars win."""
    global _CRED_LOADED
    if _CRED_LOADED:
        return
    with _CRED_LOCK:
        if _CRED_LOADED:
            return
        try:
            from dotenv import load_dotenv

            env_path = _repo_root() / ".env"
            if env_path.exists():
                load_dotenv(env_path, override=False)
        except Exception:  # noqa: BLE001 — .env is optional; never fail import
            pass
        _CRED_LOADED = True


def _gemini_api_key() -> Optional[str]:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _openai_api_key() -> Optional[str]:
    return os.getenv("OPENAI_API_KEY")


def _azure_endpoint() -> Optional[str]:
    return os.getenv("OPENAI_API_BASE") or os.getenv("AZURE_OPENAI_ENDPOINT")


def _azure_deployment() -> Optional[str]:
    return os.getenv("OPENAI_DEPLOYMENT_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT")


def _has_azure() -> bool:
    return bool(
        os.getenv("OPENAI_API_TYPE", "").lower() == "azure"
        and _openai_api_key()
        and _azure_endpoint()
        and _azure_deployment()
    )


def active_provider() -> str:
    """The provider that will actually be used: 'gemini'|'azure'|'unconfigured'."""
    load_credentials()
    if _gemini_api_key():
        return "gemini"
    if _has_azure():
        return "azure"
    return "unconfigured"


def provider_chain() -> list:
    """Ordered list of providers to try."""
    p = active_provider()
    return [p] if p != "unconfigured" else []


def is_configured() -> bool:
    return active_provider() != "unconfigured"


def gemini_model() -> str:
    load_credentials()
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def openai_model() -> str:
    load_credentials()
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def llm_timeout() -> int:
    load_credentials()
    try:
        return int(os.getenv("LLM_TIMEOUT_S", "30"))
    except (TypeError, ValueError):
        return 30


def llm_max_retries() -> int:
    load_credentials()
    try:
        return int(os.getenv("LLM_MAX_RETRIES", "2"))
    except (TypeError, ValueError):
        return 2


def is_cloud() -> bool:
    return active_provider() in ("gemini", "azure")


def build_chat_model(provider: str, temperature: float, max_tokens: Optional[int] = None):
    """Construct the LangChain chat model for a specific provider."""
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs: Dict[str, Any] = dict(
            model=gemini_model(),
            google_api_key=_gemini_api_key(),
            temperature=temperature,
            timeout=llm_timeout(),
            max_retries=llm_max_retries(),
        )
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        return ChatGoogleGenerativeAI(**kwargs)
    if provider == "azure":
        from langchain_openai import AzureChatOpenAI

        kwargs = dict(
            openai_api_key=_openai_api_key(),
            azure_endpoint=_azure_endpoint(),
            deployment_name=_azure_deployment(),
            openai_api_version=os.getenv("OPENAI_API_VERSION", "2024-05-01-preview"),
            temperature=temperature,
            timeout=llm_timeout(),
            max_retries=llm_max_retries(),
        )
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return AzureChatOpenAI(**kwargs)
    return None


def get_chat_llm():
    """Return a LangChain chat model or raise a RuntimeError if unconfigured."""
    prov = active_provider()
    if prov == "unconfigured":
        raise RuntimeError(
            "LLM not configured. Please add GEMINI_API_KEY or Azure credentials to .env."
        )
    return build_chat_model(prov, temperature=0)


# ─────────────────────────────────────────────────────────────────────────────
# LLM CLIENT  (historical .ask / .narrate / .ask_grounded surface)
# ─────────────────────────────────────────────────────────────────────────────

AGENT_CONFIG: Dict[str, Any] = {
    "model_id": "gpt-4o-mini",
    "max_new_tokens": 2048,
    "temperature": 0.3,
}

# Grounding system prompt — ensures the model ONLY uses provided data.
GROUNDING_SYSTEM = (
    "You are a senior data scientist presenting findings to VPs and heads of department. "
    "Your responses MUST be grounded exclusively in the data and numbers provided in the prompt. "
    "Do NOT invent, extrapolate, or assume any numbers not explicitly stated. "
    "If data is insufficient to answer, say so clearly. "
    "Write clear, concise, executive-level insights with specific numbers. "
    "Flag risks and opportunities. Be direct — no filler phrases. "
    "Write in plain business language. Do not use emojis, icons, or decorative symbols."
)


class LLMClient:
    """Gemini / Azure OpenAI chat client with Continum's historical method surface."""

    def __init__(self, config: Optional[Dict] = None):
        load_credentials()
        self.provider = active_provider()
        if self.provider == "unconfigured":
            raise RuntimeError(
                "LLM not configured. Please add GEMINI_API_KEY or Azure credentials to .env."
            )

        cfg = config or AGENT_CONFIG
        self.max_new_tokens = cfg.get("max_new_tokens", 2048)
        self.temperature = cfg.get("temperature", 0.3)
        if self.provider == "gemini":
            self.model_id = gemini_model()
        elif self.provider == "azure":
            self.model_id = _azure_deployment() or "gpt-4o"
        self._chat = None
        self._load_lock = threading.Lock()
        logger.info("LLMClient configured: provider=%s model=%s", self.provider, self.model_id)

    def _build_chat(self):
        return build_chat_model(self.provider, self.temperature, self.max_new_tokens)

    def _load(self) -> None:
        """Build the chat model. Cheap — no network call until first ask()."""
        if self._chat is not None:
            return
        with self._load_lock:
            if self._chat is None:
                self._chat = self._build_chat()

    def ask(self, prompt: str, system: str = "") -> str:
        self._load()
        if self._chat is None:
            raise RuntimeError(
                "LLM not configured. Please add GEMINI_API_KEY or Azure credentials to .env."
            )
        try:
            messages = [("system", system or GROUNDING_SYSTEM), ("human", prompt)]
            resp = self._chat.invoke(messages)
            return str(getattr(resp, "content", resp)).strip()
        except Exception as e:  # noqa: BLE001
            logger.error("LLMClient.ask() error: %s", e)
            return f"[LLM error: {e}]"

    def narrate(self, data: Any, context: str) -> str:
        data_str = json.dumps(data, indent=2, default=str)
        if len(data_str) > 6000:
            data_str = data_str[:6000] + "\n... [truncated]"
        return self.ask(f"{context}\n\nData:\n{data_str}")

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
            "beyond what the data shows. If results are inconclusive, say so. "
            "Use plain business language."
        )
        return self.ask(prompt, system=system)

    def unload(self) -> None:
        self._chat = None

    @property
    def is_loaded(self) -> bool:
        return self.provider != "unconfigured"

    def status(self) -> Dict:
        return {
            "model_id": self.model_id,
            "is_loaded": self.is_loaded,
            "device": self.provider,
            "provider": self.provider,
            "max_new_tokens": self.max_new_tokens,
        }


TransformersClient = LLMClient


# ─────────────────────────────────────────────────────────────────────────────
# LIFECYCLE MANAGER  (app-wide singleton client)
# ─────────────────────────────────────────────────────────────────────────────

_INSTANCE: Optional["LLMClient"] = None
_MGR_LOCK = threading.Lock()


def get_llm():
    return _INSTANCE


def require_llm(config=None):
    global _INSTANCE
    if _INSTANCE is None:
        with _MGR_LOCK:
            if _INSTANCE is None:
                _INSTANCE = LLMClient(config or AGENT_CONFIG)
                logger.info("LLMClient created (model not yet loaded)")
    return _INSTANCE


def load_llm(config=None):
    llm = require_llm(config)
    llm._load()
    return llm


def unload_llm():
    global _INSTANCE
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
    "__version__",
    "load_credentials",
    "active_provider",
    "provider_chain",
    "is_configured",
    "gemini_model",
    "openai_model",
    "llm_timeout",
    "llm_max_retries",
    "is_cloud",
    "build_chat_model",
    "get_chat_llm",
    "LLMClient",
    "TransformersClient",
    "AGENT_CONFIG",
    "GROUNDING_SYSTEM",
    "get_llm",
    "require_llm",
    "load_llm",
    "unload_llm",
    "llm_status",
]
