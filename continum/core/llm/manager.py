from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger("continum.core.llm.manager")

_INSTANCE: Optional["TransformersClient"] = None  # type: ignore
_LOCK = threading.Lock()


def get_llm():
    return _INSTANCE


def require_llm(config=None):
    global _INSTANCE
    if _INSTANCE is None:
        with _LOCK:
            if _INSTANCE is None:
                from continum.core.llm.client import TransformersClient, AGENT_CONFIG
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
            "available":    False,
            "is_loaded":    False,
            "model_id":     None,
            "device":       None,
            "max_new_tokens": 0,
            "message":      "LLM not initialised. Call /api/llm/load to start.",
        }
    s = _INSTANCE.status()
    s["available"] = True
    s["message"] = (
        f"Model loaded on {s['device']}." if s["is_loaded"]
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
