"""Continum — experimentation intelligence platform.

This package root is also the **single LLM initialisation point** for the whole
project. Credentials come from real environment variables or a repo-root
``.env`` (python-dotenv) — and nothing else. There is exactly one secrets source.

Public surface used across the codebase::

    active_provider() / is_configured() / openai_model() / load_credentials()
    get_chat_llm()                # LangChain chat model for LangGraph nodes
    LLMClient                     # historical .ask/.narrate/.ask_grounded client
    get_llm / require_llm / load_llm / unload_llm / llm_status   # lifecycle manager

Kept intentionally dependency-light: ``langchain_openai``/``langchain_google_genai``
are imported lazily and no ``continum`` submodule is imported here, so ``import
continum`` never triggers an import cycle with :mod:`continum.orchestration` /
:mod:`continum.AskData`.

Provider selection tries, in order, whichever credentials are present — Gemini
(``GEMINI_API_KEY``/``GOOGLE_API_KEY``) -> Azure -> OpenAI (``LLM_PROVIDER``
forces one). If the chosen provider's key is present but rejected at call time
(e.g. an IP-restricted or invalid key), the chat model transparently falls back
to the next configured provider instead of failing the request — see
``provider_chain()`` / ``_FallbackChat``.
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


# Providers that failed with an auth/permission error this process (e.g. an
# IP-restricted, revoked, or invalid key). Excluded from selection so we don't
# keep retrying a key we already know is rejected. Cleared only by a restart.
_DEAD_PROVIDERS: set = set()
_DEAD_LOCK = threading.Lock()


def _mark_provider_dead(provider: str) -> None:
    with _DEAD_LOCK:
        _DEAD_PROVIDERS.add(provider)


def _available_providers() -> list:
    """Providers whose credentials are present, in priority order (Gemini->Azure->OpenAI).

    Azure and plain OpenAI share ``OPENAI_API_KEY``; when the Azure quadruple is
    set we treat it as Azure only (an Azure key won't authenticate against
    api.openai.com, so listing 'openai' as a fallback would be pointless).
    """
    load_credentials()
    avail = []
    if _gemini_api_key():
        avail.append("gemini")
    if _has_azure():
        avail.append("azure")
    elif _openai_api_key():
        avail.append("openai")
    return avail


def provider_chain() -> list:
    """Ordered list of providers to try, best first.

    Honours ``LLM_PROVIDER`` (when that provider's creds exist), drops providers
    already known-dead this process, and otherwise falls back through the
    priority order. The auto-fallback client (:class:`_FallbackChat`) walks this
    list on auth failure.
    """
    avail = [p for p in _available_providers() if p not in _DEAD_PROVIDERS]
    forced = os.getenv("LLM_PROVIDER", "").strip().lower()
    if forced in avail:
        return [forced] + [p for p in avail if p != forced]
    return avail


def active_provider() -> str:
    """The provider that will actually be used first: 'gemini'|'azure'|'openai'|'unconfigured'.

    This is the head of :func:`provider_chain`, so it honours ``LLM_PROVIDER`` and
    skips any provider already known-dead this process (see :class:`_FallbackChat`).
    """
    chain = provider_chain()
    return chain[0] if chain else "unconfigured"


def is_configured() -> bool:
    return bool(provider_chain())


def gemini_model() -> str:
    load_credentials()
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def openai_model() -> str:
    load_credentials()
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


# Hard per-call request timeout (seconds) and retry cap. Without these the
# LangChain clients retry 429/5xx with exponential backoff and NO ceiling, so a
# single rate-limited call can stall the whole request into a frontend timeout
# with no answer. Override via .env if needed.
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


# ─────────────────────────────────────────────────────────────────────────────
# LANGCHAIN CHAT MODEL  (for the AskData / orchestrator LangGraph nodes)
# ─────────────────────────────────────────────────────────────────────────────

_NOT_CONFIGURED = "[LLM not configured — set GEMINI_API_KEY or OPENAI_API_KEY in .env]"


def is_cloud() -> bool:
    return active_provider() in ("gemini", "azure", "openai")


class _Unconfigured:
    """Stand-in chat model used when no credentials are present.

    ``.invoke()`` raises so callers can fall back (e.g. README answers) or surface
    a clear 'configure a key' message rather than producing garbage.
    """

    provider = "unconfigured"

    def invoke(self, *args, **kwargs):
        raise RuntimeError("No LLM configured — set GEMINI_API_KEY or OPENAI_API_KEY in .env.")


def build_chat_model(provider: str, temperature: float, max_tokens: Optional[int] = None):
    """Construct the LangChain chat model for a specific provider (no fallback)."""
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
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs = dict(
            model=openai_model(),
            openai_api_key=_openai_api_key(),
            temperature=temperature,
            timeout=llm_timeout(),
            max_retries=llm_max_retries(),
        )
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return ChatOpenAI(**kwargs)
    return None


# Substrings that mark a *credential* failure (key rejected / lacks access) as
# opposed to a transient error (429 rate-limit, 5xx, timeout). Only these trigger
# fallback to the next provider — we never fall back on transient failures.
_AUTH_ERROR_MARKERS = (
    "permission_denied",
    "permissiondenied",
    "api_key_invalid",
    "api key not valid",
    "invalid_api_key",
    "invalid api key",
    "incorrect api key",
    "unauthorized",
    "authenticationerror",
    "invalid authentication",
    "access denied",
    "ip address",
    "ip_address",
    " 401",
    " 403",
    "code': 401",
    "code': 403",
)


def _is_auth_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    if "authentication" in name or "permission" in name:
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in _AUTH_ERROR_MARKERS)


class _FallbackChat:
    """Chat model that tries providers in order, falling back on auth failure.

    Presents the ``.invoke(...)`` surface the app uses and transparently proxies
    any other attribute to the current underlying model. When a provider's call
    fails with a credential/permission error (not a transient one), that provider
    is marked dead for the rest of the process and the next provider is tried.
    """

    def __init__(self, providers, temperature: float, max_tokens: Optional[int] = None):
        self._providers = list(providers)
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._idx = 0
        self._model = None
        self._lock = threading.Lock()

    @property
    def current_provider(self) -> str:
        return self._providers[self._idx] if self._idx < len(self._providers) else "unconfigured"

    def _ensure_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = build_chat_model(
                        self._providers[self._idx], self._temperature, self._max_tokens
                    )
        return self._model

    def invoke(self, *args, **kwargs):
        last_exc: Optional[Exception] = None
        while self._idx < len(self._providers):
            prov = self._providers[self._idx]
            try:
                return self._ensure_model().invoke(*args, **kwargs)
            except Exception as e:  # noqa: BLE001 — inspected by _is_auth_error
                last_exc = e
                has_next = self._idx + 1 < len(self._providers)
                if _is_auth_error(e):
                    _mark_provider_dead(prov)
                    if has_next:
                        nxt = self._providers[self._idx + 1]
                        logger.warning(
                            "LLM provider '%s' rejected credentials (%s); falling back to '%s'",
                            prov,
                            e,
                            nxt,
                        )
                        self._idx += 1
                        self._model = None
                        continue
                raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No LLM providers available")

    def __getattr__(self, name):
        # Only reached for attributes not defined on the wrapper itself. Proxy them
        # to the current underlying model. Guard dunders/underscores to avoid
        # recursion during construction/copy/pickle.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ensure_model(), name)


def build_fallback_chat(temperature: float, max_tokens: Optional[int] = None):
    """A :class:`_FallbackChat` over the current provider chain, or None if empty."""
    chain = provider_chain()
    if not chain:
        return None
    return _FallbackChat(chain, temperature, max_tokens)


def get_chat_llm():
    """Return a LangChain chat model: tries configured providers in priority order
    (gemini -> azure -> openai) and auto-falls-back to the next one on an auth
    error, or a raising stub when nothing is configured."""
    return build_fallback_chat(temperature=0) or _Unconfigured()


# ─────────────────────────────────────────────────────────────────────────────
# LLM CLIENT  (historical .ask / .narrate / .ask_grounded surface)
# ─────────────────────────────────────────────────────────────────────────────

AGENT_CONFIG: Dict[str, Any] = {
    "model_id": "gpt-4o-mini",  # default; overridden by OPENAI_MODEL env
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
    """OpenAI / Azure OpenAI chat client with Continum's historical method surface."""

    def __init__(self, config: Optional[Dict] = None):
        load_credentials()
        cfg = config or AGENT_CONFIG
        self.max_new_tokens = cfg.get("max_new_tokens", 2048)
        self.temperature = cfg.get("temperature", 0.3)
        self.provider = active_provider()
        if self.provider == "gemini":
            self.model_id = gemini_model()
        elif self.provider == "azure":
            self.model_id = _azure_deployment() or "gpt-4o"
        else:
            self.model_id = openai_model()
        self._chat = None
        self._load_lock = threading.Lock()
        logger.info("LLMClient configured: provider=%s model=%s", self.provider, self.model_id)

    def _build_chat(self):
        # Auto-falls-back across providers (gemini -> azure -> openai) on auth
        # failure; None when nothing is configured.
        return build_fallback_chat(self.temperature, self.max_new_tokens)

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
            return _NOT_CONFIGURED
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
        return is_configured()

    def status(self) -> Dict:
        # Report the provider actually in use — after an auto-fallback the live
        # provider can differ from the one chosen at construction time.
        prov = self.provider
        if self._chat is not None and hasattr(self._chat, "current_provider"):
            prov = self._chat.current_provider
        return {
            "model_id": self.model_id,
            "is_loaded": self.is_loaded,
            "device": prov,  # 'gemini' | 'azure' | 'openai' | 'unconfigured'
            "provider": prov,
            "max_new_tokens": self.max_new_tokens,
        }


# Back-compatible alias — historical imports of ``TransformersClient`` (now OpenAI-backed).
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
    "build_fallback_chat",
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
