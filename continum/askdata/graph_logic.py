"""
AskData multi-agent LangGraph workflow (ported from the upstream AskData
project's ``graph_logic.py``).

Changes from upstream:
  * ``get_llm()`` delegates to :func:`continum.askdata.llm.get_chat_llm`
    so the same graph runs on Azure OpenAI, standard OpenAI, or the local Qwen
    fallback depending on available credentials.
  * Imports are package-relative (``from .metadata import get_metadata``).
  * ``_clean_sql`` replaces the fragile ``.replace('sql', '')`` markdown cleanup
    with a fence-aware stripper that won't mangle identifiers containing "sql".

The node logic and graph topology are otherwise unchanged.
"""

import json
import logging
import re
from io import StringIO
from typing import List, Optional, TypedDict

import pandas as pd
from langgraph.graph import END, StateGraph

from .llm import get_chat_llm
from .metadata import get_metadata

logger = logging.getLogger("continum.askdata.graph_logic")


# Define the state
class GraphState(TypedDict):
    user_question: str
    refined_question: Optional[str]
    history: str  # Summarized history
    structured_context: Optional[str]  # JSON string of filters/entities
    plan: List[str]
    current_step_index: int
    sql_query: Optional[str]
    dataframe_json: Optional[str]
    visualizations: Optional[List[dict]]
    insight: Optional[str]
    retry_count: int
    error: Optional[str]
    final_output: Optional[dict]


def get_llm():
    """Return the active chat model (Azure / OpenAI / local fallback)."""
    return get_chat_llm()


def _clean_sql(raw: str) -> str:
    """Strip markdown code fences and a leading 'sql' language tag from LLM output."""
    text = (raw or "").strip()
    # Remove ```sql ... ``` or ``` ... ``` fences.
    fence = re.match(r"^```(?:sql)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    else:
        text = text.replace("```", "").strip()
        # A bare leading "sql" language hint on its own line/word.
        text = re.sub(r"^sql\s+", "", text, flags=re.IGNORECASE)
    return text.strip()


# --- Plan normalization (keeps the viz branch reachable) ---
#
# The orchestrator LLM emits a free-text plan. Two failure modes silently break
# the graph: (a) a token that isn't one of our routable agents (e.g. "visualize",
# "chart", "summarise") dead-ends the conditional router, and (b) the LLM simply
# omits "viz" for a question that clearly wants a chart. _normalize_plan maps
# synonyms to the canonical agent names, drops unknown tokens, guarantees
# 'refine' precedes 'sql', and forces 'viz' in when the user asked for a visual
# or whenever new data is fetched (the viz node's own guard then decides whether
# a chart actually helps). This is the structural half of "visualizations never
# show"; the deterministic fallback in visualization_node is the other half.

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

    # 'refine' is MANDATORY before 'sql' (the orchestrator prompt says so, but the
    # LLM sometimes forgets) — insert it so the sql node gets a refined question.
    if "sql" in out and "refine" not in out:
        out.insert(out.index("sql"), "refine")

    wants_viz = bool(_VIZ_INTENT.search(user_question or ""))
    # New data is being fetched → always attempt a chart (the node guard + the
    # deterministic fallback decide if one is actually shown). Also honor an
    # explicit "chart/plot/trend/..." request even on a data-less follow-up.
    if ("sql" in out or wants_viz) and "viz" not in out:
        # viz comes after sql/refine but the node only needs a dataframe, so append.
        out.append("viz")

    return out or ["refine", "sql", "viz"]


def _fallback_chart(df) -> Optional[dict]:
    """Build a sensible default Plotly config when the LLM declines a chart but the
    data is clearly chartable (caller guarantees >=2 rows, >=2 cols, a numeric col).

    Picks a time column for a line chart if present, else the first categorical
    column for a bar chart, against the first numeric column.
    """
    try:
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        non_numeric = [c for c in df.columns if c not in numeric_cols]
        if not numeric_cols:
            return None
        y = numeric_cols[0]
        # Prefer a date/time-like column for the x axis (→ line chart).
        time_cols = [
            c
            for c in df.columns
            if re.search(r"date|time|day|week|month|period", str(c), re.IGNORECASE)
        ]
        if time_cols:
            x, ctype = time_cols[0], "line"
        elif non_numeric:
            x, ctype = non_numeric[0], "bar"
        else:
            # all-numeric: chart the second column against the first.
            x, ctype = df.columns[0], "bar"
            y = numeric_cols[1] if len(numeric_cols) > 1 else numeric_cols[0]
        cfg = {"type": ctype, "x": str(x), "y": str(y), "title": f"{y} by {x}"}
        # Add a series split if a second categorical column exists.
        extra_cat = [c for c in non_numeric if c != x]
        if extra_cat:
            cfg["color"] = str(extra_cat[0])
        return cfg
    except Exception:
        logger.exception("fallback chart construction failed")
        return None


# --- Node Functions ---


def orchestrator_node(state: GraphState):
    logger.info("Entering orchestrator_node")
    llm = get_llm()
    user_question = state["user_question"]
    history = state["history"]
    structured_context = state.get("structured_context", "{}")
    metadata = get_metadata()
    domain_context = metadata["domain_context"]
    table_info = metadata["table_info_combined"]
    table_descriptions = metadata.get("table_descriptions", {})

    # --- Automated Semantic Reset Detection ---
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

    reset_response = llm.invoke(reset_prompt)
    logger.info(f"Reset check response: {reset_response.content.strip()}")
    try:
        reset_content = reset_response.content.strip()
        if "```json" in reset_content:
            reset_content = reset_content.split("```json")[1].split("```")[0].strip()
        reset_action = json.loads(reset_content).get("action", "RETAIN")
    except Exception as e:
        logger.warning(f"Failed to parse reset action: {e}")
        reset_action = "RETAIN"

    logger.info(f"Reset action determined: {reset_action}")
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

    response = llm.invoke(prompt)
    logger.info(f"Orchestrator plan response: {response.content.strip()}")
    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        plan_data = json.loads(content)
        plan = plan_data.get("plan", ["refine", "sql", "viz"])
    except Exception as e:
        logger.warning(f"Failed to parse orchestrator plan: {e}")
        plan = ["refine", "sql", "viz"]

    plan = _normalize_plan(plan, user_question)
    logger.info(f"Final plan (normalized): {plan}")
    return {
        "plan": plan,
        "history": current_history,
        "structured_context": current_context,
        "current_step_index": 0,
        "retry_count": 0,
        "error": None,
        "final_output": None,
    }


def intent_refinement_node(state: GraphState):
    logger.info("Entering intent_refinement_node")
    llm = get_llm()
    user_question = state["user_question"]
    history = state["history"]
    structured_context = state.get("structured_context", "{}")
    metadata = get_metadata()
    domain_context = metadata["domain_context"]
    table_info = metadata["table_info_combined"]

    prompt = f"""
    You are a Query Refinement Expert for an {domain_context} data assistant.
    Your primary goal is to map the user's natural language request to the provided Database Schema, using the conversation history ONLY to resolve ambiguities or references.

    ### DATABASE SCHEMA (Primary Source of Truth):
    {table_info}

    ### CONTEXT (Secondary):
    History Summary: {history}
    Structured State: {structured_context}

    ### USER QUESTION:
    {user_question}

    ### INSTRUCTIONS:
    1. ALWAYS prioritize the Database Schema. If the user mentions a term, find its closest equivalent in the schema columns or tables.
    2. Resolve any references (e.g., "it", "them", "that city", "previous group") by looking at the History and Structured State.
    2. If it's a follow-up, merge the previous constraints with the new question.
       Example:
       Turn 1: "Show sales for Bangalore"
       Turn 2: "What about Chennai?"
       Refined: "Show sales for Chennai"
    3. If the user uses pronouns (e.g., "their revenue"), resolve them to the specific entities previously mentioned.
    4. If the question is already self-contained, return it as is.
    5. Return ONLY a JSON object with a single key 'refined_question'.
    """

    response = llm.invoke(prompt)
    logger.info(f"Refinement response: {response.content.strip()}")
    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        refined_data = json.loads(content)
        refined_question = refined_data.get("refined_question", user_question)
    except Exception as e:
        logger.warning(f"Failed to parse refined question: {e}")
        refined_question = user_question

    logger.info(f"Refined question: {refined_question}")
    return {
        "refined_question": refined_question,
        "current_step_index": state["current_step_index"] + 1,
    }


def sql_node(state: GraphState, db_connection):
    logger.info("Entering sql_node")
    llm = get_llm()
    user_question = state.get("refined_question") or state["user_question"]
    history = state["history"]
    structured_context = state.get("structured_context", "{}")
    retry_count = state.get("retry_count", 0)
    error = state.get("error")

    metadata = get_metadata()
    domain_context = metadata["domain_context"]
    column_descriptions = metadata["column_descriptions"]
    relationships = metadata["relationships"]
    table_info_combined = metadata["table_info_combined"]
    table_descriptions = metadata.get("table_descriptions", {})

    if error:
        system_msg = f"You are a SQL Self-Correction Expert for {domain_context}. The previous SQL failed with error: {error}. Focus on fixing column names and join conditions based on the Database Schema."
        user_prompt = f"""
        ### DATABASE SCHEMA (Source of Truth):
        Tables and Columns: {json.dumps(column_descriptions, indent=2)}
        Table Info (DDL-like): {table_info_combined}
        Table Descriptions: {json.dumps(table_descriptions, indent=2)}

        ### ERROR DIAGNOSTIC:
        The previous query failed.
        Error: {error}

        ### TASK:
        1. Review the Schema above. Ensure every column used exists in the 'Tables and Columns' JSON.
        2. Check for common SQLite errors (e.g., string vs integer).
        3. Provide a CORRECTED SELECT query.

        Return ONLY the corrected SQLite SELECT query.
        """
    else:
        system_msg = f"You are an {domain_context} SQLite expert. Your primary task is to translate natural language into SQL based on the official Database Schema."
        user_prompt = f"""
        ### DATABASE SCHEMA (Primary Source of Truth):
        Tables and Columns:
        {json.dumps(column_descriptions, indent=2)}
        Relationships: {json.dumps(relationships, indent=2)}
        Table Info (DDL-like): {table_info_combined}

        ### CONTEXT (Secondary):
        History: {history}
        Structured State: {structured_context}

        ### CURRENT REQUEST:
        User Question: {user_question}

        ### INSTRUCTIONS:
        1. ALWAYS prioritize the Database Schema over the conversation history. If there is a conflict, the Schema wins.
        2. Use the 'Structured State' and 'History' ONLY to resolve references or to understand the user's iterative refinement of a query.
        - If the current question is a follow-up (e.g., "What about Bangalore?"), carry forward the previous metrics and constraints unless contradicted.
        - Return ONLY valid SQLite SELECT query.
        - No markdown, no comments.
        - LIMIT results to 50 unless specified.
        - Round numerical values to 2 decimal places.
        """

    response = llm.invoke(
        [
            ("system", system_msg),
            ("human", user_prompt),
        ]
    )
    logger.info(f"SQL generation response: {response.content.strip()}")

    sql_query = _clean_sql(response.content)
    logger.info(f"Executing SQL: {sql_query}")

    try:
        df = pd.read_sql_query(sql_query, db_connection)
        logger.info(f"SQL execution successful, returned {len(df)} rows.")
        return {
            "sql_query": sql_query,
            "dataframe_json": df.to_json(),
            "error": None,
            "retry_count": 0,
            "current_step_index": state["current_step_index"] + 1,
        }
    except Exception as e:
        logger.error(f"SQL execution failed: {str(e)}")
        # If it failed, don't increment step index, but increment retry count
        return {
            "sql_query": sql_query,
            "error": str(e),
            "retry_count": retry_count + 1,
        }


def visualization_node(state: GraphState):
    logger.info("Entering visualization_node")
    llm = get_llm()
    user_question = state["user_question"]
    df_json = state.get("dataframe_json")

    if not df_json:
        return {"current_step_index": state["current_step_index"] + 1}

    df = pd.read_json(StringIO(df_json))
    # Deterministic guard: a chart only makes sense for a comparable set of values.
    # Skip it for empty results, a single row, a single scalar/column, or a result
    # with no numeric column to plot — those read better as text/table than a chart.
    n_rows, n_cols = df.shape
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if df.empty or n_rows < 2 or n_cols < 2 or not numeric_cols:
        logger.info(
            "visualization_node: skipping chart (rows=%s cols=%s numeric=%s)",
            n_rows,
            n_cols,
            len(numeric_cols),
        )
        return {"visualizations": [], "current_step_index": state["current_step_index"] + 1}

    data_sample = df.head(5).to_dict(orient="records")
    column_info = df.dtypes.apply(lambda x: str(x)).to_dict()

    viz_prompt = f"""
    You are a data visualization expert. Suggest a Plotly Express chart (line, bar, pie)
    ONLY when a chart genuinely helps the user read the answer.

    User Question: {user_question}
    Data Sample: {data_sample}
    Columns: {column_info}

    Return an EMPTY list [] (no chart) when a visual would not help, e.g.:
    - the answer is a single value / single row, or a yes-no / textual answer
    - there is no meaningful category-vs-metric or time-vs-metric relationship to show
    - the data is just an ID list or a raw record dump with no comparison
    - a table already conveys the answer more clearly than a chart would
    Prefer NO chart over a weak or misleading one.

    Mapping Rules:
    - For a trend over time -> use 'line' (x = the date/time column, y = the numeric metric).
    - For comparing several groups/series across the SAME x (e.g. revenue per product_family
      over date, or Treatment vs Control over time) -> use 'line' (or 'bar') AND set 'color' to
      the categorical column that distinguishes the series. This renders one line per series.
    - For comparisons between a few categories -> use 'bar' chart.
    - For distributions or percentages of a total -> use 'pie' chart.

    Series / color rules:
    - 'color' MUST be an exact column name present in the data that splits rows into series
      (e.g. 'product_family', 'group_name', 'cohort', 'city'). Omit 'color' for a single series.
    - 'x', 'y' and 'color' must be exact column names from the Columns list above.

    Strict Rules:
    - Limit to ONLY ONE best fitting visual.
    - Return ONLY a JSON list containing a single object (or an empty list if no visual is suitable).

    Output:
    Return ONLY the JSON list of objects with: 'type', 'x', 'y', 'values', 'names', 'color', 'title'.
    """

    response = llm.invoke(
        [
            ("system", "Return ONLY a JSON list of Plotly chart configurations."),
            ("human", viz_prompt),
        ]
    )
    logger.info(f"Visualization response: {response.content.strip()}")

    try:
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        configs = json.loads(content)
        if not isinstance(configs, list):
            configs = [configs] if isinstance(configs, dict) else []
    except Exception:
        logger.warning("visualization_node: could not parse chart config; using fallback")
        configs = []

    # Deterministic fallback: the data passed the chartable guard above, so if the
    # LLM declined (or returned junk) build a sensible default rather than showing
    # nothing. This is the fix for "visualizations don't show up at all" — a weak
    # LLM response no longer silently drops the chart.
    if not configs:
        fb = _fallback_chart(df)
        if fb is not None:
            logger.info(
                "visualization_node: LLM returned no chart; using deterministic fallback %s", fb
            )
            configs = [fb]

    return {
        "visualizations": configs,
        "current_step_index": state["current_step_index"] + 1,
    }


def insight_node(state: GraphState):
    logger.info("Entering insight_node")
    llm = get_llm()
    user_question = state["user_question"]
    df_json = state.get("dataframe_json")
    metadata = get_metadata()
    domain_context = metadata["domain_context"]

    if not df_json:
        return {
            "insight": "No data available.",
            "current_step_index": state["current_step_index"] + 1,
        }

    df = pd.read_json(StringIO(df_json))

    table_info = metadata["table_info_combined"]
    table_descriptions = metadata.get("table_descriptions", {})

    analysis_focus = ""
    if "experimental" in domain_context.lower():
        analysis_focus = """
        When interpreting results for experimental testing:
        - Compare 'Treatment' vs 'Control' groups.
        - Look for incremental lift in GMV, Household Counts, or Orders.
        - Analyze performance differences across 'Acquisition' and 'Retention' cohorts.
        - Mention if the results suggest the campaign was successful based on the delta between groups.
        """

    insight_prompt = f"""
    You are a senior {domain_context}.
    Interpret the data results based on the User Question and the Database Schema.

    ### DATABASE SCHEMA:
    {table_info}
    {json.dumps(table_descriptions, indent=2)}

    ### USER QUESTION:
    {user_question}

    ### DATA RESULTS:
    {df.to_string()}

    {analysis_focus}

    Provide:
    What's happening
    Why it's happening
    Recommended business actions
    """

    response = llm.invoke(insight_prompt)
    logger.info(f"Insight response: {response.content.strip()[:100]}...")
    return {
        "insight": response.content,
        "current_step_index": state["current_step_index"] + 1,
    }


def clarification_node(state: GraphState):
    logger.info("Entering clarification_node")
    llm = get_llm()
    metadata = get_metadata()
    table_info = metadata["table_info_combined"]

    prompt = f"""
    The SQL assistant failed to generate a valid query for the user.
    Based on the available tables and columns, suggest 3 sample questions the user could ask instead.

    Database Schema:
    {table_info}

    Return ONLY the 3 questions as a bulleted list.
    """

    suggestions = llm.invoke(prompt).content.strip()
    logger.info(f"Clarification suggestions: {suggestions}")

    message = (
        "I'm sorry, I'm having trouble generating a valid query for your request after several attempts. "
        "Here are some alternative questions you might find useful based on the data I have:\n\n"
        f"{suggestions}"
    )

    return {
        "sql_query": None,  # Clear invalid SQL
        "insight": message,
        "current_step_index": len(state["plan"]),  # Ensure we finish after this
    }


def summarizer_node(state: GraphState):
    logger.info("Entering summarizer_node")
    llm = get_llm()
    history = state.get("history", "")
    structured_context = state.get("structured_context", "{}")
    user_question = state["user_question"]
    sql = state.get("sql_query", "")
    insight = state.get("insight")
    df_json = state.get("dataframe_json")

    # If insight wasn't generated but we have data, generate a one-liner description
    if not insight and df_json:
        df = pd.read_json(StringIO(df_json))
        if not df.empty:
            desc_prompt = f"""
            You are a helpful data assistant. Provide a one-line description of the results for the user's question.
            User Question: {user_question}
            Data:
            {df.head(10).to_string()}

            Return ONLY the one-line description.
            """
            insight = llm.invoke(desc_prompt).content.strip()

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
       - 'active_filters': dictionary of column-value pairs (e.g. {{"city": "Bangalore"}})
       - 'active_metrics': list of columns user is interested in (e.g. ["revenue_inr", "liters_sold"])
       - 'last_entities': list of specific IDs or names mentioned.
       - 'intent': the current analytical goal (e.g. "comparing city performance")

    Return ONLY a JSON object with 'history' and 'structured_context' keys.
    """

    response = llm.invoke(summary_prompt)
    logger.info(f"Summarizer response: {response.content.strip()}")
    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        result = json.loads(content)
        new_history = result.get("history", history)
        new_structured_context = json.dumps(result.get("structured_context", {}))
    except Exception as e:
        logger.warning(f"Failed to parse summarizer output: {e}")
        new_history = history
        new_structured_context = structured_context

    # Also prepare the final output
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


# --- Router Functions ---


def router(state: GraphState):
    logger.info("Entering router")
    plan = state["plan"]
    idx = state["current_step_index"]

    # Skip any token that isn't a routable agent (defense-in-depth on top of
    # _normalize_plan) so an unexpected plan entry can never dead-end the graph.
    while idx < len(plan) and plan[idx] not in _KNOWN_AGENTS:
        logger.warning("router: skipping unknown plan token %r", plan[idx])
        idx += 1

    if idx >= len(plan):
        logger.info("Plan complete, routing to summarize.")
        return "summarize"

    next_node = plan[idx]
    logger.info(f"Routing to next node in plan: {next_node}")
    return next_node


# --- Graph Construction ---


def route_from_orchestrator(state: GraphState):
    return router(state)


def route_from_sql(state: GraphState):
    if state.get("error"):
        if state.get("retry_count", 0) <= 3:
            return "retry"
        else:
            return "ask_clarification"
    return router(state)


def create_graph(db_connection):
    workflow = StateGraph(GraphState)

    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("intent_refinement", intent_refinement_node)
    workflow.add_node("sql_agent", lambda state: sql_node(state, db_connection))
    workflow.add_node("viz_agent", visualization_node)
    workflow.add_node("insight_agent", insight_node)
    workflow.add_node("summarize_agent", summarizer_node)
    workflow.add_node("ask_clarification", clarification_node)

    workflow.set_entry_point("orchestrator")

    workflow.add_conditional_edges(
        "orchestrator",
        route_from_orchestrator,
        {
            "refine": "intent_refinement",
            "sql": "sql_agent",
            "viz": "viz_agent",
            "insight": "insight_agent",
            "summarize": "summarize_agent",
        },
    )

    workflow.add_conditional_edges(
        "intent_refinement",
        router,
        {
            "refine": "intent_refinement",
            "sql": "sql_agent",
            "viz": "viz_agent",
            "insight": "insight_agent",
            "summarize": "summarize_agent",
        },
    )

    workflow.add_conditional_edges(
        "sql_agent",
        route_from_sql,
        {
            "retry": "sql_agent",
            "refine": "intent_refinement",
            "sql": "sql_agent",
            "viz": "viz_agent",
            "insight": "insight_agent",
            "summarize": "summarize_agent",
            "ask_clarification": "ask_clarification",
        },
    )

    workflow.add_edge("ask_clarification", "summarize_agent")

    workflow.add_conditional_edges(
        "viz_agent",
        router,
        {
            "sql": "sql_agent",
            "viz": "viz_agent",
            "insight": "insight_agent",
            "summarize": "summarize_agent",
        },
    )

    workflow.add_conditional_edges(
        "insight_agent",
        router,
        {
            "sql": "sql_agent",
            "viz": "viz_agent",
            "insight": "insight_agent",
            "summarize": "summarize_agent",
        },
    )

    workflow.add_edge("summarize_agent", END)

    return workflow.compile()
