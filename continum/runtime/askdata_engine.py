import os
import json
import logging
import pandas as pd
from io import StringIO
from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, END
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from continum.runtime.ask import (
    detect_intent, extract_entities, Intent,
    reason_why_dropped, reason_significance, reason_next_step,
    reason_longitudinal, reason_causal_explain, reason_cohort,
    reason_assumption, reason_summarise, ReasoningChain
)

# Configure logging
logger = logging.getLogger("continum.runtime.askdata_engine")

# Define the state
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
    reasoning_output: Optional[str]
    reasoning_chain: Optional[dict]
    retry_count: int
    error: Optional[str]
    final_output: Optional[dict]
    # Add PersistIQ specific context
    ui_context: Optional[dict]
    # Runtime objects
    session: Any
    bus: Any
    memory: Any

def get_llm():
    if os.getenv("OPENAI_API_KEY"):
        return AzureChatOpenAI(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            azure_endpoint=os.getenv("OPENAI_API_BASE"),
            deployment_name=os.getenv("OPENAI_DEPLOYMENT_NAME"),
            openai_api_version=os.getenv("OPENAI_API_VERSION"),
            temperature=0
        )
    else:
        from continum.core.llm.manager import get_llm as get_internal_llm
        internal_llm = get_internal_llm()
        if internal_llm:
            class InternalLLMWrapper:
                def invoke(self, prompt):
                    if isinstance(prompt, list):
                        combined_prompt = ""
                        for m in prompt:
                            if hasattr(m, 'content'):
                                combined_prompt += f"{m.content}\n"
                            else:
                                combined_prompt += f"{str(m)}\n"
                        res = internal_llm.ask(combined_prompt)
                    else:
                        res = internal_llm.ask(str(prompt))

                    class Response:
                        def __init__(self, content):
                            self.content = content
                    return Response(res)
            return InternalLLMWrapper()
        return None

# --- Node Functions ---
from continum.runtime.askdata_metadata import get_metadata

def orchestrator_node(state: GraphState, db):
    logger.info("Entering orchestrator_node")
    llm = get_llm()
    user_question = state["user_question"]

    if not llm:
        logger.warning("LLM not available, falling back to rule-based planning")
        return {"plan": ["reasoning", "summarize"], "current_step_index": 0}

    ui_context = state.get("ui_context", {})
    metadata = get_metadata(db)
    table_info = metadata["table_info_combined"]

    session = state.get("session")
    active_exp = getattr(session, "active_experiment", "None") if session else "None"

    prompt = f"""
    You are an orchestrator for PersistIQ AskData assistant.
    Current UI Context: {json.dumps(ui_context)}
    Active Experiment: {active_exp}

    ### DATABASE SCHEMA:
    {table_info}

    Available agents:
    - 'refine': To map user request to schema and resolve references.
    - 'reasoning': For reasoning over active experiment results, session state, and historical patterns (Copilot logic).
    - 'sql': For generating and executing SQL queries on raw/aggregated data.
    - 'viz': For generating visualizations.
    - 'insight': For generating final business insights by synthesizing all findings.

    Plan the execution based on the user question and context.
    If the question is about "why" something happened in an experiment, "significance", or "next steps", use 'reasoning'.
    If the question needs specific data lookups or comparisons not in the session, use 'sql'.

    Return ONLY a JSON object with 'plan' key.

    Example: {{"plan": ["reasoning", "insight"]}} or {{"plan": ["refine", "sql", "insight"]}}

    User Question: {user_question}
    """

    response = llm.invoke(prompt)
    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        plan = json.loads(content).get("plan", ["refine", "sql", "insight"])
    except:
        plan = ["refine", "sql", "insight"]

    return {"plan": plan, "current_step_index": 0}

def intent_refinement_node(state: GraphState, db):
    logger.info("Entering intent_refinement_node")
    llm = get_llm()
    user_question = state["user_question"]
    history = state["history"]
    ui_context = state.get("ui_context", {})
    metadata = get_metadata(db)
    table_info = metadata["table_info_combined"]

    prompt = f"""
    Refine the user question for PersistIQ.
    UI Context: {json.dumps(ui_context)}
    Schema: {table_info}
    History: {history}
    User Question: {user_question}

    Return ONLY a JSON object with 'refined_question'.
    """
    response = llm.invoke(prompt)
    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        refined_question = json.loads(content).get("refined_question", user_question)
    except:
        refined_question = user_question

    return {"refined_question": refined_question, "current_step_index": state["current_step_index"] + 1}

def reasoning_node(state: GraphState):
    logger.info("Entering reasoning_node")
    question = state["user_question"]
    session = state.get("session")
    bus = state.get("bus")
    memory = state.get("memory")
    db = getattr(session, "db", None) if session else None

    intent = detect_intent(question)
    entities = extract_entities(question)

    # Reasoning logic from Copilot
    response = ""
    chain = ReasoningChain()

    exp = getattr(session, "active_experiment", "this experiment") if session else "this experiment"

    hypothesis_map = {
        Intent.WHY_DROPPED: f"The treatment caused a metric drop in '{exp}'.",
        Intent.WHY_IMPROVED: f"The treatment caused a genuine improvement in '{exp}'.",
        Intent.SIGNIFICANCE: f"'{exp}' has a statistically significant effect.",
        Intent.CAUSAL_EXPLAIN: f"The observed effect in '{exp}' is causally driven by the treatment."
    }
    chain.set_hypothesis(hypothesis_map.get(intent, f"'{exp}' produced a meaningful result."))
    chain.build_from_context(session, bus, memory)

    if intent in (Intent.WHY_DROPPED, Intent.INVESTIGATE, Intent.SEGMENT_EXPLAIN, Intent.WHY_IMPROVED):
        response = reason_why_dropped(question, entities, session, bus, memory)
    elif intent == Intent.SIGNIFICANCE:
        base = reason_significance(session, bus)
        response = f"{base}\n\n  {chain.synthesise()}"
    elif intent == Intent.NEXT_STEP:
        response = reason_next_step(session, bus, memory)
    elif intent == Intent.CAUSAL_EXPLAIN:
        response = reason_causal_explain(question, entities, session, bus)
    elif intent == Intent.SUMMARISE:
        response = reason_summarise(session, bus, memory)
    elif intent == Intent.LONGITUDINAL:
        response = reason_longitudinal(question, session, memory)
    elif intent == Intent.COHORT:
        response = reason_cohort(session, db)
    elif intent == Intent.ASSUMPTION:
        response = reason_assumption(session)
    else:
        # Fallback to general reasoning if no specific intent matched but reasoning node was called
        response = chain.render()

    return {
        "reasoning_output": response,
        "reasoning_chain": chain.to_dict(),
        "current_step_index": state["current_step_index"] + 1
    }

def sql_node(state: GraphState, db):
    logger.info("Entering sql_node")
    llm = get_llm()
    user_question = state.get("refined_question") or state["user_question"]
    metadata = get_metadata(db)
    table_info = metadata["table_info_combined"]

    prompt = f"""
    Generate a DuckDB SQL query for the following request:
    {user_question}

    Schema:
    {table_info}

    Return ONLY the SQL query. No markdown.
    """
    response = llm.invoke(prompt)
    sql_query = response.content.strip().replace("```sql", "").replace("```", "").strip()

    try:
        df = db.execute(sql_query).df()
        return {
            "sql_query": sql_query,
            "dataframe_json": df.to_json(),
            "current_step_index": state["current_step_index"] + 1
        }
    except Exception as e:
        return {"error": str(e), "retry_count": state.get("retry_count", 0) + 1}

def visualization_node(state: GraphState):
    logger.info("Entering visualization_node")
    return {"visualizations": [], "current_step_index": state["current_step_index"] + 1}

def insight_node(state: GraphState):
    logger.info("Entering insight_node")
    llm = get_llm()
    user_question = state["user_question"]
    df_json = state.get("dataframe_json")
    reasoning_output = state.get("reasoning_output")

    history = state.get("history", "")

    context_parts = []
    if reasoning_output:
        context_parts.append(f"PRE-COMPUTED REASONING:\n{reasoning_output}")
    if df_json:
        df = pd.read_json(StringIO(df_json))
        context_parts.append(f"DATABASE QUERY RESULT:\n{df.to_string()}")

    if not context_parts:
        return {"insight": "I couldn't find specific data or reasoning to answer that question.", "current_step_index": state["current_step_index"] + 1}

    context = "\n\n".join(context_parts)

    prompt = f"""
    You are the PersistIQ Insight Agent. Synthesize a final answer for the user.

    User Question: {user_question}

    Context Information:
    {context}

    Additional History:
    {history}

    Provide a concise, professional insight and recommendations. Use markdown for formatting.
    """
    response = llm.invoke(prompt)
    return {"insight": response.content, "current_step_index": state["current_step_index"] + 1}

def summarizer_node(state: GraphState):
    logger.info("Entering summarizer_node")
    final_output = {
        "sql": state.get("sql_query"),
        "dataframe": state.get("dataframe_json"),
        "visualizations": state.get("visualizations"),
        "insight": state.get("insight"),
        "reasoning": state.get("reasoning_output"),
        "chain": state.get("reasoning_chain")
    }
    return {"final_output": final_output}

# --- Router ---
def router(state: GraphState):
    plan = state["plan"]
    idx = state["current_step_index"]
    if idx >= len(plan):
        return "summarize"
    step = plan[idx]
    if step in ["refine", "reasoning", "sql", "viz", "insight", "summarize"]:
        return step
    return "insight" # Fallback

def create_askdata_graph(db):
    workflow = StateGraph(GraphState)
    workflow.add_node("orchestrator", lambda s: orchestrator_node(s, db))
    workflow.add_node("refine", lambda s: intent_refinement_node(s, db))
    workflow.add_node("reasoning", reasoning_node)
    workflow.add_node("sql", lambda s: sql_node(s, db))
    workflow.add_node("viz", visualization_node)
    workflow.add_node("insight", insight_node)
    workflow.add_node("summarize", summarizer_node)

    workflow.set_entry_point("orchestrator")

    workflow.add_conditional_edges("orchestrator", router, {
        "refine": "refine", "reasoning": "reasoning", "sql": "sql", "viz": "viz", "insight": "insight", "summarize": "summarize"
    })
    workflow.add_conditional_edges("refine", router, {
        "refine": "refine", "reasoning": "reasoning", "sql": "sql", "viz": "viz", "insight": "insight", "summarize": "summarize"
    })
    workflow.add_conditional_edges("reasoning", router, {
        "refine": "refine", "reasoning": "reasoning", "sql": "sql", "viz": "viz", "insight": "insight", "summarize": "summarize"
    })
    workflow.add_conditional_edges("sql", lambda s: "retry" if s.get("error") and s.get("retry_count", 0) < 3 else router(s), {
        "retry": "sql", "refine": "refine", "reasoning": "reasoning", "sql": "sql", "viz": "viz", "insight": "insight", "summarize": "summarize"
    })
    workflow.add_conditional_edges("viz", router, {
        "refine": "refine", "reasoning": "reasoning", "sql": "sql", "viz": "viz", "insight": "insight", "summarize": "summarize"
    })
    workflow.add_conditional_edges("insight", router, {
        "refine": "refine", "reasoning": "reasoning", "sql": "sql", "viz": "viz", "insight": "insight", "summarize": "summarize"
    })
    workflow.add_edge("summarize", END)

    return workflow.compile()

class AskDataEngine:
    def __init__(self, db):
        self.db = db
        self.graph = create_askdata_graph(db)

    def ask(self, question, history="", ui_context=None, session=None, bus=None, memory=None):
        initial_state = {
            "user_question": question,
            "history": history,
            "current_step_index": 0,
            "plan": [],
            "ui_context": ui_context or {},
            "session": session,
            "bus": bus,
            "memory": memory,
            "retry_count": 0
        }
        result = self.graph.invoke(initial_state)
        final = result.get("final_output", {})

        # Return a structure compatible with both simple string response and chain response
        return {
            "answer": final.get("insight") or final.get("reasoning") or "No response generated.",
            "reasoning": final.get("reasoning"),
            "chain": final.get("chain"),
            "sql": final.get("sql"),
            "dataframe": final.get("dataframe")
        }
