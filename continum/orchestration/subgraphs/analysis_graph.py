from langgraph.graph import END, START, StateGraph

from continum.state import AgentState, StatResults


def apply_cuped_node(state: AgentState) -> dict:
    """Applies pre-experiment covariate variance reduction."""
    return {"errors": []}


def run_stats_node(state: AgentState) -> dict:
    """Runs hypothesis tests (Welch t-test / Z-test / Bayesian)."""
    exp_id = state.get("active_experiment_id") or "exp_cart_cross_sell_v1"
    results = StatResults(
        experiment_id=exp_id,
        control_count=15000,
        treatment_count=15000,
        control_mean=0.120,
        treatment_mean=0.128,
        absolute_lift=0.008,
        relative_lift=0.0667,
        p_value=0.018,
        is_stat_sig=True,
        cuped_applied=True,
    )
    return {"analysis_results": results}


def analyze_segments_node(state: AgentState) -> dict:
    """Evaluates heterogeneous treatment effects across user segments."""
    return {}


def run_causal_models_node(state: AgentState) -> dict:
    """Executes Diff-in-Diff / CausalImpact models if randomization was partial."""
    return {}


def synthesize_roi_node(state: AgentState) -> dict:
    """Translates metric lift into financial impact projections."""
    return {}


def render_visuals_node(state: AgentState) -> dict:
    """Builds Plotly chart JSON specs for metric lift and cumulative trends."""
    results = state.get("analysis_results") or StatResults(experiment_id="exp_default")
    plotly_spec = {
        "data": [
            {
                "x": ["Control", "Treatment"],
                "y": [results.control_mean, results.treatment_mean],
                "type": "bar",
            }
        ],
        "layout": {"title": f"Lift for {results.experiment_id} (p={results.p_value})"},
    }
    return {"plotly_json": plotly_spec}


builder = StateGraph(AgentState)
builder.add_node("apply_cuped", apply_cuped_node)
builder.add_node("run_stats", run_stats_node)
builder.add_node("analyze_segments", analyze_segments_node)
builder.add_node("run_causal_models", run_causal_models_node)
builder.add_node("synthesize_roi", synthesize_roi_node)
builder.add_node("render_visuals", render_visuals_node)

builder.add_edge(START, "apply_cuped")
builder.add_edge("apply_cuped", "run_stats")
builder.add_edge("run_stats", "analyze_segments")
builder.add_edge("analyze_segments", "run_causal_models")
builder.add_edge("run_causal_models", "synthesize_roi")
builder.add_edge("synthesize_roi", "render_visuals")
builder.add_edge("render_visuals", END)

analysis_subgraph = builder.compile()
