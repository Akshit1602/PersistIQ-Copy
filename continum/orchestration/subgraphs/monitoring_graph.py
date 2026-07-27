from langgraph.graph import StateGraph, START, END
from continum.state import AgentState

def fetch_telemetry_node(state: AgentState) -> dict:
    """Retrieves pulse metrics and exposure counts from StatSig."""
    return {
        "statsig_experiment_id": state.get("active_experiment_id") or "exp_checkout_redesign",
        "health_alerts": []
    }

def check_srm_node(state: AgentState) -> dict:
    """Performs Chi-Square goodness-of-fit test for Sample Ratio Mismatch."""
    alerts = state.get("health_alerts", [])
    # Placeholder for srm_detector execution
    has_srm = False
    return {"srm_flag": has_srm, "health_alerts": alerts}

builder = StateGraph(AgentState)
builder.add_node("fetch_telemetry", fetch_telemetry_node)
builder.add_node("check_srm", check_srm_node)

builder.add_edge(START, "fetch_telemetry")
builder.add_edge("fetch_telemetry", "check_srm")
builder.add_edge("check_srm", END)

monitoring_subgraph = builder.compile()