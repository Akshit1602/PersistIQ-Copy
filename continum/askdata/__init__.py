"""
AskData — the multi-agent LangGraph data assistant, integrated into Continum.

Ported from the standalone AskData project (Streamlit + LangGraph + Azure
OpenAI).  Inside Continum it runs behind the Copilot pane and works on Azure
OpenAI, standard OpenAI, or a local fallback model depending on configured
credentials.

Public surface:
    get_askdata_engine(app=None) -> AskDataGraphEngine
    AskDataGraphEngine.ask(question, ui_context=None) -> dict
"""
from .engine import AskDataGraphEngine, get_askdata_engine
from .llm import active_provider, is_cloud, get_chat_llm
from .metadata import get_metadata, get_active_dataset_name, list_datasets

__all__ = [
    "AskDataGraphEngine",
    "get_askdata_engine",
    "active_provider",
    "is_cloud",
    "get_chat_llm",
    "get_metadata",
    "get_active_dataset_name",
    "list_datasets",
    "AnalyticsGroundedAskEngine", "get_ask_engine", "run_ask", "AskIntent",
]

from .ask_engine import AnalyticsGroundedAskEngine, get_ask_engine, run_ask, AskIntent
