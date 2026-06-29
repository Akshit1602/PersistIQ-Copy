import os
import json
import logging
import pandas as pd
from io import StringIO
from typing import TypedDict, List, Optional, Literal
from langgraph.graph import StateGraph, END
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

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
    retry_count: int
    error: Optional[str]
    final_output: Optional[dict]
    # Add PersistIQ specific context
    ui_context: Optional[dict]

def get_llm():
    # Attempt to use Azure OpenAI if configured, else fall back to a compatible interface
    # For PersistIQ, we might want to use the internal TransformersClient if Azure is not available,
    # but AskData's logic is heavily tuned for GPT-4 level models.
    # We'll check for environment variables first.
    if os.getenv("OPENAI_API_KEY"):
        return AzureChatOpenAI(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            azure_endpoint=os.getenv("OPENAI_API_BASE"),
            deployment_name=os.getenv("OPENAI_DEPLOYMENT_NAME"),
            openai_api_version=os.getenv("OPENAI_API_VERSION"),
            temperature=0
        )
    else:
        # Fallback to internal LLM if available
        from continum.core.llm.manager import get_llm as get_internal_llm
        internal_llm = get_internal_llm()
        if internal_llm:
            class InternalLLMWrapper:
                def invoke(self, prompt):
                    if isinstance(prompt, list):
                        # Convert list of messages to a single string
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
    if not llm:
        return {"error": "LLM not available"}

    user_question = state["user_question"]
    history = state["history"]
    structured_context = state.get("structured_context", "{}")
    ui_context = state.get("ui_context", {})
    metadata = get_metadata(db)
    table_info = metadata["table_info_combined"]

    prompt = f"""
    You are an orchestrator for PersistIQ AskData assistant.
    Current UI Context: {json.dumps(ui_context)}

    ### DATABASE SCHEMA:
    {table_info}

    Available agents:
    - 'refine': To map user request to schema and resolve references.
    - 'sql': For generating and executing SQL queries.
    - 'viz': For generating visualizations.
    - 'insight': For generating business insights.

    Plan the execution based on the user question and context.
    Be efficient: only include 'sql' or 'viz' if explicitly needed to answer.
    For simple greeting or non-data questions, just return ['insight'].
    Return ONLY a JSON object with 'plan' key.

    User Question: {user_question}
    """

    response = llm.invoke(prompt)
    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        plan = json.loads(content).get("plan", ["refine", "sql", "viz", "insight"])
    except:
        plan = ["refine", "sql", "viz", "insight"]

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
    # Simplified viz node for now
    return {"visualizations": [], "current_step_index": state["current_step_index"] + 1}

def insight_node(state: GraphState, db):
    logger.info("Entering insight_node")
    llm = get_llm()
    user_question = state["user_question"]
    df_json = state.get("dataframe_json")
    if not df_json:
        return {"insight": "No data to analyze.", "current_step_index": state["current_step_index"] + 1}

    df = pd.read_json(StringIO(df_json))
    history = state.get("history", "")
    prompt = f"""
    Analyze this data for the user question: {user_question}
    Data:
    {df.to_string()}

    Additional Context/History:
    {history}

    Provide insights and recommendations.
    """
    response = llm.invoke(prompt)
    return {"insight": response.content, "current_step_index": state["current_step_index"] + 1}

def summarizer_node(state: GraphState):
    logger.info("Entering summarizer_node")
    final_output = {
        "sql": state.get("sql_query"),
        "dataframe": state.get("dataframe_json"),
        "visualizations": state.get("visualizations"),
        "insight": state.get("insight")
    }
    return {"final_output": final_output}

# --- Router ---
def router(state: GraphState):
    plan = state["plan"]
    idx = state["current_step_index"]
    if idx >= len(plan):
        return "summarize"
    return plan[idx]

def create_askdata_graph(db):
    workflow = StateGraph(GraphState)
    workflow.add_node("orchestrator", lambda s: orchestrator_node(s, db))
    workflow.add_node("refine", lambda s: intent_refinement_node(s, db))
    workflow.add_node("sql", lambda s: sql_node(s, db))
    workflow.add_node("viz", visualization_node)
    workflow.add_node("insight", lambda s: insight_node(s, db))
    workflow.add_node("summarize", summarizer_node)

    workflow.set_entry_point("orchestrator")

    workflow.add_conditional_edges("orchestrator", router, {
        "refine": "refine", "sql": "sql", "viz": "viz", "insight": "insight", "summarize": "summarize"
    })
    workflow.add_conditional_edges("refine", router, {
        "refine": "refine", "sql": "sql", "viz": "viz", "insight": "insight", "summarize": "summarize"
    })
    workflow.add_conditional_edges("sql", lambda s: "retry" if s.get("error") and s.get("retry_count", 0) < 3 else router(s), {
        "retry": "sql", "refine": "refine", "sql": "sql", "viz": "viz", "insight": "insight", "summarize": "summarize"
    })
    workflow.add_conditional_edges("viz", router, {
        "sql": "sql", "viz": "viz", "insight": "insight", "summarize": "summarize"
    })
    workflow.add_conditional_edges("insight", router, {
        "sql": "sql", "viz": "viz", "insight": "insight", "summarize": "summarize"
    })
    workflow.add_edge("summarize", END)

    return workflow.compile()

class AskDataEngine:
    def __init__(self, db):
        self.db = db
        self.graph = create_askdata_graph(db)

    def ask(self, question, history="", ui_context=None):
        initial_state = {
            "user_question": question,
            "history": history,
            "current_step_index": 0,
            "plan": [],
            "ui_context": ui_context or {}
        }
        result = self.graph.invoke(initial_state)
        return result.get("final_output", {}).get("insight", "No response generated.")
