"""The AskData multi-agent LangGraph, wired by the orchestrator.

Topology (unchanged from the proven engine):

    orchestrator(plan) → refine → sql (generate+execute on DuckDB) → viz → insight → summarize

The node *bodies* for refine / sql / viz / insight / clarify live in the AskData
generators (:mod:`continum.AskData`); this module owns the planner, the summarizer
(which persists multi-turn state), the routers, and graph construction. The chat
model is :func:`continum.get_chat_llm`; SQL executes on the injected DuckDB.
"""

from __future__ import annotations

import functools
import json
import logging
import re
from io import StringIO
from typing import List, Optional, TypedDict

import pandas as pd
from langgraph.graph import END, StateGraph

from continum import get_chat_llm
from continum.AskData import (
    clarification_node,
    describe_result,
    insight_node,
    refine_node,
    sql_node,
    visualization_node,
)
from continum.mapMeta import get_metadata

logger = logging.getLogger("continum.orchestration.graph")


class GraphState(TypedDict):
    user_question: str
    refined_question: Optional[str]
    history: str
    structured_context: Optional[str]
    plan: List[str]
    current_step_index: int
    sql_query: Optional[str]
    dataframe_json: Optional[str]
    visualizations: Optional[List[dict]]
    insight: Optional[str]
    retry_count: int
    error: Optional[str]
    final_output: Optional[dict]


def _llm():
    return get_chat_llm()


# ── Plan normalization (keeps the viz branch reachable) ──────────────────────
_KNOWN_AGENTS = ("refine", "sql", "viz", "insight")

_AGENT_SYNONYMS = {
    "refine": "refine",
    "refinement": "refine",
    "intent": "refine",
    "sql": "sql",
    "query": "sql",
    "data": "sql",
    "viz": "viz",
    "visualization": "viz",
    "visualisation": "viz",
    "visualize": "viz",
    "visualise": "viz",
    "chart": "viz",
    "plot": "viz",
    "graph": "viz",
    "insight": "insight",
    "insights": "insight",
    "analysis": "insight",
    "explain": "insight",
    "recommend": "insight",
    "recommendation": "insight",
}

_VIZ_INTENT = re.compile(
    r"\b(chart|plot|graph|visuali[sz]e|visuali[sz]ation|trend|over time|"
    r"by (month|week|day|segment|variant|group|category|region|cohort)|"
    r"distribution|breakdown|compare|comparison|per )\b",
    re.IGNORECASE,
)


def _normalize_plan(plan, user_question: str) -> List[str]:
    raw = plan if isinstance(plan, list) else [plan]
    out: List[str] = []
    for tok in raw:
        canon = _AGENT_SYNONYMS.get(str(tok).strip().lower())
        if canon and canon not in out:
            out.append(canon)
    if "sql" in out and "refine" not in out:
        out.insert(out.index("sql"), "refine")
    wants_viz = bool(_VIZ_INTENT.search(user_question or ""))
    if ("sql" in out or wants_viz) and "viz" not in out:
        out.append("viz")
    return out or ["refine", "sql", "viz"]


# ── Planner + summarizer (state-owning nodes) ────────────────────────────────


def orchestrator_node(state: GraphState):
    logger.info("Entering orchestrator_node")
    llm = _llm()
    user_question = state["user_question"]
    history = state["history"]
    structured_context = state.get("structured_context", "{}")
    metadata = get_metadata()
    domain_context = metadata["domain_context"]
    table_info = metadata["table_info_combined"]
    table_descriptions = metadata.get("table_descriptions", {})

    reset_prompt = f"""
    Analyze the user's question against the Database Schema and current conversation state.

    ### DATABASE SCHEMA:
    {table_info}
    {json.dumps(table_descriptions, indent=2)}

    ### CONTEXT:
    Current State (JSON): {structured_context}
    User Question: {user_question}

    Determine if the user wants to:
    1. 'RETAIN': Continue the current thread or refine it.
    2. 'RESET': Start a completely new topic or explicitly asked for a reset.

    Return ONLY a JSON object with 'action' (RETAIN/RESET).
    """
    try:
        reset_content = llm.invoke(reset_prompt).content.strip()
        if "```json" in reset_content:
            reset_content = reset_content.split("```json")[1].split("```")[0].strip()
        reset_action = json.loads(reset_content).get("action", "RETAIN")
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to parse reset action: %s", e)
        reset_action = "RETAIN"

    current_history = history if reset_action == "RETAIN" else ""
    current_context = structured_context if reset_action == "RETAIN" else "{}"

    prompt = f"""
    You are an orchestrator for a {domain_context} data assistant.
    Analyze the user's question against the Database Schema first to decide the execution plan.

    ### DATABASE SCHEMA:
    {table_info}
    {json.dumps(table_descriptions, indent=2)}

    Available agents:
    - 'refine': To map user request to schema and resolve references. MANDATORY before 'sql'.
    - 'sql': For generating and executing SQL queries when new data is needed.
    - 'viz': For generating visualizations from data.
    - 'insight': For generating business insights, analysis, or explanations from data.

    Rules:
    1. ALWAYS prioritize matching the question to the Database Schema.
    2. If the user asks for a new data query, the plan should be ["refine", "sql", "viz"].
    3. If the user asks for a change in visualization and data is already available, the plan should be ["viz"].
    4. If the user asks for business insights, analysis, "why", "explain", or recommendations, INCLUDE 'insight' in the plan.
    5. If the user asks a follow-up that requires new data but NOT insights, the plan should be ["refine", "sql", "viz"].
    6. If the question can be answered from existing data/history without a new SQL, skip 'sql'.
    7. Return ONLY a JSON object with the 'plan' key (a list of agent names).

    User Question: {user_question}
    History Summary: {current_history}
    """
    try:
        content = llm.invoke(prompt).content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        plan = json.loads(content).get("plan", ["refine", "sql", "viz"])
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to parse orchestrator plan: %s", e)
        plan = ["refine", "sql", "viz"]

    plan = _normalize_plan(plan, user_question)
    logger.info("Final plan (normalized): %s", plan)
    return {
        "plan": plan,
        "history": current_history,
        "structured_context": current_context,
        "current_step_index": 0,
        "retry_count": 0,
        "error": None,
        "final_output": None,
    }


def summarizer_node(state: GraphState):
    logger.info("Entering summarizer_node")
    llm = _llm()
    history = state.get("history", "")
    structured_context = state.get("structured_context", "{}")
    user_question = state["user_question"]
    sql = state.get("sql_query", "")
    insight = state.get("insight")
    df_json = state.get("dataframe_json")

    if not insight and df_json:
        try:
            df = pd.read_json(StringIO(df_json))
            if not df.empty:
                insight = describe_result(df, user_question, llm)
        except Exception:  # noqa: BLE001
            pass

    summary_prompt = f"""
    You are a conversation state manager for a SQL assistant.
    Analyze the new turn and update the conversation history AND the structured context.

    Current History: {history}
    Current Structured Context: {structured_context}

    New Turn:
    User: {user_question}
    SQL: {sql}
    Result Snapshot: {insight}

    Your Task:
    1. Update the 'History' summary (concise narrative).
    2. Update the 'StructuredContext' JSON. It must track:
       - 'active_filters': dictionary of column-value pairs
       - 'active_metrics': list of columns user is interested in
       - 'last_entities': list of specific IDs or names mentioned.
       - 'intent': the current analytical goal

    Return ONLY a JSON object with 'history' and 'structured_context' keys.
    """
    try:
        content = llm.invoke(summary_prompt).content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        result = json.loads(content)
        new_history = result.get("history", history)
        new_structured_context = json.dumps(result.get("structured_context", {}))
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to parse summarizer output: %s", e)
        new_history = history
        new_structured_context = structured_context

    final_output = {
        "sql": state.get("sql_query"),
        "dataframe": state.get("dataframe_json"),
        "visualizations": state.get("visualizations"),
        "insight": insight,
    }
    return {
        "history": new_history,
        "structured_context": new_structured_context,
        "final_output": final_output,
    }


# ── Routers ──────────────────────────────────────────────────────────────────


def router(state: GraphState):
    plan = state["plan"]
    idx = state["current_step_index"]
    while idx < len(plan) and plan[idx] not in _KNOWN_AGENTS:
        logger.warning("router: skipping unknown plan token %r", plan[idx])
        idx += 1
    if idx >= len(plan):
        return "summarize"
    return plan[idx]


def route_from_sql(state: GraphState):
    if state.get("error"):
        if state.get("retry_count", 0) <= 3:
            return "retry"
        return "ask_clarification"
    return router(state)


# ── Graph construction ────────────────────────────────────────────────────────


def create_graph(db_connection, llm=None):
    """Compile the AskData graph bound to a DuckDB connection.

    The refine/viz/insight/clarify node bodies come from the AskData generators;
    ``sql`` is bound to ``db_connection`` (DuckDB). ``llm`` defaults to the shared
    chat model, fetched lazily inside each node when omitted.
    """
    workflow = StateGraph(GraphState)

    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("intent_refinement", functools.partial(refine_node, llm=llm))
    workflow.add_node("sql_agent", functools.partial(sql_node, db=db_connection, llm=llm))
    workflow.add_node("viz_agent", functools.partial(visualization_node, llm=llm))
    workflow.add_node("insight_agent", functools.partial(insight_node, llm=llm))
    workflow.add_node("summarize_agent", summarizer_node)
    workflow.add_node("ask_clarification", functools.partial(clarification_node, llm=llm))

    workflow.set_entry_point("orchestrator")

    _edges = {
        "refine": "intent_refinement",
        "sql": "sql_agent",
        "viz": "viz_agent",
        "insight": "insight_agent",
        "summarize": "summarize_agent",
    }
    workflow.add_conditional_edges("orchestrator", router, _edges)
    workflow.add_conditional_edges("intent_refinement", router, _edges)
    workflow.add_conditional_edges(
        "sql_agent",
        route_from_sql,
        {"retry": "sql_agent", "ask_clarification": "ask_clarification", **_edges},
    )
    workflow.add_edge("ask_clarification", "summarize_agent")
    workflow.add_conditional_edges("viz_agent", router, _edges)
    workflow.add_conditional_edges("insight_agent", router, _edges)
    workflow.add_edge("summarize_agent", END)

    return workflow.compile()


__all__ = ["GraphState", "create_graph", "_normalize_plan"]
