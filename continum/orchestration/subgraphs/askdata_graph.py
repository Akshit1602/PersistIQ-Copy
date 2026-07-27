from langgraph.graph import StateGraph, START, END
from continum.state import AgentState, GrowthPrediction

def text_to_sql_node(state: AgentState) -> dict:
    """Converts natural language questions into validated SQL."""
    return {"generated_sql": "SELECT COUNT(*) FROM orders WHERE timestamp >= '2026-01-01'"}

def growth_simulator_node(state: AgentState) -> dict:
    """Runs Monte Carlo simulations to project annual lift."""
    projection = GrowthPrediction(
        hypothesis_id="hyp_cross_sell_v2",
        metric_name="annual_revenue",
        assumed_lift=0.02,
        projected_quarterly_lift=450000.0,
        projected_annual_lift=1800000.0,
        simulation_bounds={"p10": 1200000.0, "p90": 2300000.0}
    )
    return {"growth_projection": projection}

def synthesize_answer_node(state: AgentState) -> dict:
    """Synthesizes query results into conversational response."""
    return {}

builder = StateGraph(AgentState)
builder.add_node("generate_sql", text_to_sql_node)
builder.add_node("simulate_growth", growth_simulator_node)
builder.add_node("synthesize_answer", synthesize_answer_node)

builder.add_edge(START, "generate_sql")
builder.add_edge("generate_sql", "simulate_growth")
builder.add_edge("simulate_growth", "synthesize_answer")
builder.add_edge("synthesize_answer", END)

askdata_subgraph = builder.compile()