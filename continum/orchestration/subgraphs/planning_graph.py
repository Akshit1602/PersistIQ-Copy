from langgraph.graph import END, START, StateGraph

from continum.state import AgentState, ExperimentBrief


def brief_generator_node(state: AgentState) -> dict:
    """Drafts hypothesis and target segment skeleton."""
    brief = state.get("brief") or ExperimentBrief()
    if state["messages"]:
        brief.hypothesis = state["messages"][-1].content
    return {"brief": brief}


def metric_planner_node(state: AgentState) -> dict:
    """Selects primary, secondary, and guardrail metrics."""
    brief = state.get("brief") or ExperimentBrief()
    brief.primary_metric = brief.primary_metric or "conversion_rate"
    brief.guardrail_metrics = ["latency_ms", "error_rate"]
    return {"brief": brief}


def opportunity_sizing_node(state: AgentState) -> dict:
    """Calculates historical baseline rates and revenue potential."""
    brief = state.get("brief") or ExperimentBrief()
    brief.baseline_conversion_rate = 0.12
    brief.baseline_variance = 0.1056
    return {"brief": brief}


def power_calculator_node(state: AgentState) -> dict:
    """Calculates required sample size and test duration."""
    brief = state.get("brief") or ExperimentBrief()
    brief.mde = brief.mde or 0.03
    brief.required_sample_size = 42500
    brief.estimated_duration_days = 14
    return {"brief": brief}


def traffic_balance_node(state: AgentState) -> dict:
    """Computes traffic split ratios between control and treatment variants."""
    return {"brief": state.get("brief")}


builder = StateGraph(AgentState)
builder.add_node("generate_brief", brief_generator_node)
builder.add_node("plan_metrics", metric_planner_node)
builder.add_node("size_opportunity", opportunity_sizing_node)
builder.add_node("calculate_power", power_calculator_node)
builder.add_node("balance_traffic", traffic_balance_node)

builder.add_edge(START, "generate_brief")
builder.add_edge("generate_brief", "plan_metrics")
builder.add_edge("plan_metrics", "size_opportunity")
builder.add_edge("size_opportunity", "calculate_power")
builder.add_edge("calculate_power", "balance_traffic")
builder.add_edge("balance_traffic", END)

planning_subgraph = builder.compile()
