from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from continum.state import AgentState
from continum.config import settings
from continum.orchestration.tools.registry import all_experimentation_tools
from continum.orchestration.tools.subgraph_tools import subgraph_tools

# Combine individual tools and subgraph tools
combined_tools = all_experimentation_tools + subgraph_tools

SUPERVISOR_PROMPT = """
You are Continum, an AI Retail Experimentation Assistant.
Your goal is to help users plan, monitor, analyze, and predict outcomes for retail A/B tests.

GUIDELINES:
1. Answer general questions or definitions directly in concise Markdown prose.
2. For multi-step workflows (planning a test, running full analysis, checking SRM, querying database):
   ALWAYS invoke the corresponding tool or subgraph tool.
3. NEVER calculate sample sizes, p-values, or revenue lifts yourself—always rely on tool output.
"""

def supervisor_agent_node(state: AgentState) -> dict:
    """Conversational ReAct Supervisor Agent."""
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE
    )
    
    if combined_tools:
        llm = llm.bind_tools(combined_tools)

    messages = [SystemMessage(content=SUPERVISOR_PROMPT)] + state["messages"]
    response = llm.invoke(messages)

    return {"messages": [response]}

def should_continue(state: AgentState):
    """Checks if tool execution is required."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools_node"
    return END

# Build Graph
supervisor_builder = StateGraph(AgentState)
supervisor_builder.add_node("supervisor", supervisor_agent_node)

if combined_tools:
    supervisor_builder.add_node("tools_node", ToolNode(combined_tools))
    supervisor_builder.add_conditional_edges("supervisor", should_continue, ["tools_node", END])
    supervisor_builder.add_edge("tools_node", "supervisor")
else:
    supervisor_builder.add_edge("supervisor", END)

supervisor_builder.add_edge(START, "supervisor")

app_graph = supervisor_builder.compile()