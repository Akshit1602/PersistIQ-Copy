"""
LLM factory for the AskData LangGraph engine.

Returns a LangChain chat model (``.invoke(...)``-shaped) for the active provider,
selected from credentials by :mod:`continum.crosscutting.llm`:

    azure        -> AzureChatOpenAI
    openai       -> ChatOpenAI
    unconfigured -> a stub whose .invoke() raises, so callers fall back cleanly
                    (e.g. the engine answers "about itself" from the README, and
                    data questions return a clear "configure OPENAI_API_KEY" note).

Credentials come from real env vars, a repo-root ``.env``, or
``.streamlit/secrets.toml`` (handled centrally by ``core.llm.config``).
"""
from __future__ import annotations

import logging
import os

from continum.crosscutting.llm import (
    load_credentials, active_provider, openai_model,
)

logger = logging.getLogger("continum.askdata.llm")


def is_cloud() -> bool:
    return active_provider() in ("azure", "openai")


class _Unconfigured:
    """Stand-in chat model used when no LLM credentials are present.

    Raises on use so callers can fall back (README answers) or surface a clear
    'configure OpenAI' message rather than producing garbage.
    """
    provider = "unconfigured"

    def invoke(self, *args, **kwargs):
        raise RuntimeError(
            "OpenAI is not configured - set OPENAI_API_KEY in .streamlit/secrets.toml or .env."
        )


def get_chat_llm():
    """Return a chat model for the active provider (azure | openai | unconfigured)."""
    provider = active_provider()

    if provider == "azure":
        from langchain_openai import AzureChatOpenAI
        return AzureChatOpenAI(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            azure_endpoint=os.getenv("OPENAI_API_BASE") or os.getenv("AZURE_OPENAI_ENDPOINT"),
            deployment_name=os.getenv("OPENAI_DEPLOYMENT_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            openai_api_version=os.getenv("OPENAI_API_VERSION", "2024-05-01-preview"),
            temperature=0,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=openai_model(), temperature=0)

    return _Unconfigured()


__all__ = [
    "get_chat_llm",
    "active_provider",
    "is_cloud",
    "load_credentials",
]
