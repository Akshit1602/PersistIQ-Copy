from typing import Dict, Any
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from continum.config import settings
from continum.state import AgentState
from continum.orchestration.tools.registry import all_experimentation_tools

# Instantiate LLM dynamically (Gemini if GEMINI_API_KEY is in .env, otherwise OpenAI)
llm = settings.get_llm()
llm_with_tools = llm.bind_tools(all_experimentation_tools)


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """
    ReAct Supervisor Agent node that determines user intent, calls tools,
    and synthesizes results for the user.
    """
    system_prompt = (
        "You are Continum's A/B Testing & Retail Experimentation Copilot. "
        "Always use deterministic ExpSuite tools for all statistical calculations, "
        "CUPED variance reduction, SRM checks, and power sizing. "
        "Never fabricate or hallucinate statistical numbers, p-values, or confidence intervals."
    )
    
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    
    return {"messages": [response]}


# Construct LangGraph Workflow with ReAct Tool Loop
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("tools", ToolNode(all_experimentation_tools))

# Add Edges
workflow.add_edge(START, "supervisor")
workflow.add_conditional_edges("supervisor", tools_condition)
workflow.add_edge("tools", "supervisor")

# Compile graph with thread checkpointer
memory = MemorySaver()
app_graph = workflow.compile(checkpointer=memory)