import logging

from langgraph.graph import END, START, StateGraph

from continum.askdata import ChartGeneratorInput, generate_visualization
from continum.ExpSuite.causal import DiDInput, calculate_diff_in_diff
from continum.ExpSuite.stats_inference import (
    CUPEDInput,
    StatTestInput,
    apply_cuped,
    calculate_hypothesis_test,
)
from continum.state import AnalysisState, UIArtifact

logger = logging.getLogger(__name__)


def _supplied(**kwargs) -> dict:
    """Drops unsupplied keys so each input model applies its declared default."""
    return {key: value for key, value in kwargs.items() if value is not None}


def _missing(state: AnalysisState, *names: str) -> list:
    return [name for name in names if state.get(name) is None]


def _effective_means(state: AnalysisState) -> tuple:
    """
    The means the hypothesis test ran on: CUPED-adjusted when variance reduction
    was applied, observed otherwise. Shared so the chart cannot drift from the
    numbers the test actually used.
    """
    cuped = state.get("cuped_result")
    if cuped:
        return cuped["control_cuped_mean"], cuped["treatment_cuped_mean"]
    return state.get("control_mean"), state.get("treatment_mean")


def apply_cuped_node(state: AnalysisState) -> dict:
    """Applies pre-experiment covariate variance reduction."""
    if not state.get("use_cuped"):
        return {}

    absent = _missing(state, "y_control", "x_control", "y_treatment", "x_treatment")
    if absent:
        return {
            "errors": [
                "CUPED requested but pre-period covariates were not supplied: " + ", ".join(absent)
            ]
        }

    result = apply_cuped(
        CUPEDInput(
            y_control=state["y_control"],
            x_control=state["x_control"],
            y_treatment=state["y_treatment"],
            x_treatment=state["x_treatment"],
        )
    )
    return {"cuped_result": result.model_dump()}


def run_stats_node(state: AnalysisState) -> dict:
    """Runs hypothesis tests (Welch t-test / Z-test / Bayesian)."""
    absent = _missing(
        state,
        "control_mean",
        "control_std",
        "control_count",
        "treatment_mean",
        "treatment_std",
        "treatment_count",
    )
    if absent:
        return {"missing_inputs": absent}

    # When CUPED ran, use its adjusted means — that is the whole point of
    # running it — while keeping the observed dispersion and counts.
    control_mean, treatment_mean = _effective_means(state)

    result = calculate_hypothesis_test(
        StatTestInput(
            **_supplied(
                control_mean=control_mean,
                control_std=state["control_std"],
                control_count=state["control_count"],
                treatment_mean=treatment_mean,
                treatment_std=state["treatment_std"],
                treatment_count=state["treatment_count"],
                alpha=state.get("alpha"),
            )
        )
    )
    return {
        "stat_result": result.model_dump(),
        "statistical_significance": result.is_stat_sig,
    }


def analyze_segments_node(state: AnalysisState) -> dict:
    """Evaluates heterogeneous treatment effects across user segments."""
    # Segment-level analysis has no implementation in continum today. The
    # function that backed it, `ExpSuite/analysis/segment.py::run_segment_analysis`,
    # was removed in 496c76d and is tracked for recovery. Report that plainly
    # rather than returning an empty result that reads as "no heterogeneity found".
    return {
        "errors": [
            "Segment analysis is not implemented: no backend function is wired "
            "for heterogeneous treatment effects."
        ]
    }


def run_causal_models_node(state: AnalysisState) -> dict:
    """Executes Diff-in-Diff / CausalImpact models if randomization was partial."""
    absent = _missing(state, "control_pre", "control_post", "treatment_pre", "treatment_post")
    if absent:
        # DiD is opt-in: absent pre/post means simply mean the caller did not ask
        # for an observational estimate, so this is not an error.
        return {}

    result = calculate_diff_in_diff(
        DiDInput(
            control_pre=state["control_pre"],
            control_post=state["control_post"],
            treatment_pre=state["treatment_pre"],
            treatment_post=state["treatment_post"],
        )
    )
    return {"causal_result": result.model_dump()}


def synthesize_roi_node(state: AnalysisState) -> dict:
    """Translates metric lift into financial impact projections."""
    stat = state.get("stat_result")
    if not stat:
        return {}

    domain_context = state.get("domain_context") or "ecomm"
    domain_basis = (
        "Focusing on digital funnel metrics (AOV, Quote Approval, Conversion Rate)."
        if domain_context == "ecomm"
        else "Focusing on physical store retail metrics (Basket Size, Zone Dwell Time, POS Velocity)."
    )

    # Deliberately arithmetic-only over an already-computed lift.
    return {
        "roi_summary": {
            "absolute_lift": stat["absolute_lift"],
            "relative_lift": stat["relative_lift"],
            "ci_lower": stat["ci_lower"],
            "ci_upper": stat["ci_upper"],
            "is_stat_sig": stat["is_stat_sig"],
            "domain_context": domain_context,
            "basis": f"{domain_basis} Derived from hypothesis test results.",
        }
    }


def render_visuals_node(state: AnalysisState) -> dict:
    """
    Builds the metric-lift chart and emits it as a UIArtifact.

    Without the artifact the chart existed only in subgraph state and never
    reached the SSE stream, so an analysis that had computed a perfectly good
    comparison still rendered in chat as text alone.
    """
    stat = state.get("stat_result")
    if not stat:
        logger.info("render_visuals skipped: the hypothesis test produced no result")
        return {}

    control_mean, treatment_mean = _effective_means(state)
    chart = generate_visualization(
        ChartGeneratorInput(
            chart_type="metric_lift",
            title=f"Lift for {state.get('active_experiment_id') or 'experiment'}",
            data={
                "control_mean": control_mean,
                "treatment_mean": treatment_mean,
                "ci_lower": stat["ci_lower"],
                "ci_upper": stat["ci_upper"],
                "metric_name": state.get("primary_metric") or "Value",
            },
        )
    )
    if chart.chart_spec is None:
        logger.warning("render_visuals: %s", chart.summary)
        return {}

    logger.info("render_visuals: rendered metric_lift chart")
    return {
        "chart_spec": chart.chart_spec.model_dump(),
        "plotly_json": chart.plotly_json,
        "ui_artifacts": [
            UIArtifact(
                artifact_id="art_analysis_metric_lift",
                type="plotly_chart",
                title=chart.chart_spec.title,
                payload={"chart_spec": chart.chart_spec.model_dump(), "summary": chart.summary},
            )
        ],
    }


builder = StateGraph(AnalysisState)
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
