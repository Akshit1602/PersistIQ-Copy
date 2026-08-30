"""
AskData routing: SQL, visualization, and growth insights.

Previously a fixed SQL -> growth-simulate -> synthesize chain, which forced every
question through a Monte Carlo simulation and skipped visualization entirely. The
three concerns are independent, so the graph now branches to whichever the caller
actually asked for. `run_askdata_workflow` in `orchestration/tools/subgraph_tools.py`
is correspondingly split into three tools, letting the agent combine them the same
way it combines the atomic ExpSuite tools.

The SQL branch no longer terminates at the rows. It routes on to `auto_chart`
whenever the result is chartable, because a model that has to decide "should I
also call the chart tool?" mostly decides not to -- which is why questions that
obviously wanted a picture came back as a wall of numbers. The decision is
deterministic (`AskData.derive_chart_spec`) and logged on both outcomes, so a
missing chart always has a checkable reason in the server log.
"""

import logging

from langgraph.graph import END, START, StateGraph

from continum.AskData import (
    ChartGeneratorInput,
    ChartSpec,
    GrowthSimulationInput,
    SQLExecutionInput,
    derive_chart_spec,
    execute_sql_query,
    generate_visualization,
    simulate_and_visualize_growth,
    summarize_spec,
)
from continum.state import AskDataState, UIArtifact

logger = logging.getLogger(__name__)


def _supplied(**kwargs) -> dict:
    """Drops unsupplied keys so each input model applies its declared default."""
    return {key: value for key, value in kwargs.items() if value is not None}


def _chart_artifact(spec: ChartSpec, artifact_id: str, summary: str) -> UIArtifact:
    """
    Wraps a chart spec as the UIArtifact the SSE layer forwards to MatchView.

    Only the spec travels, not the Plotly figure: the frontend renders the spec
    as SVG, and the figure is kilobytes of layout that would also land in the
    LLM's context via the tool result.
    """
    return UIArtifact(
        artifact_id=artifact_id,
        type="plotly_chart",
        title=spec.title,
        payload={"chart_spec": spec.model_dump(), "summary": summary},
    )


def route_request(state: AskDataState) -> str:
    """
    Picks the branch the caller supplied inputs for. Checked most specific first:
    an explicit chart request wins over a bare query, and forecast parameters win
    over both, because only one branch runs per invocation.
    """
    if state.get("baseline_monthly_revenue") is not None:
        return "simulate_growth"
    if state.get("chart_type"):
        return "render_chart"
    if state.get("query"):
        return "run_sql"
    return "report_missing"


def run_sql_node(state: AskDataState) -> dict:
    """Executes a validated read-only query against the configured warehouse."""
    result = execute_sql_query(SQLExecutionInput(query=state["query"]))
    update = {
        "generated_sql": result.sql_statement,
        "sql_summary": result.summary,
        "row_count": result.row_count,
    }
    if not result.is_safe:
        update["errors"] = [result.summary]
        return update
    update["query_results"] = result.rows
    return update


def route_after_sql(state: AskDataState) -> str:
    """
    Sends chartable results on to `auto_chart`. Suppressed when the caller
    explicitly passed visualize=False, and skipped (with a logged reason) when
    the rows hold nothing worth plotting.
    """
    if state.get("visualize") is False:
        logger.info("auto_chart skipped: caller passed visualize=False")
        return "end"
    rows = state.get("query_results") or []
    if not rows:
        logger.info("auto_chart skipped: query returned no rows")
        return "end"
    if derive_chart_spec(rows, title=state.get("chart_title") or "") is None:
        logger.info(
            "auto_chart skipped: %d row(s) with columns %s held no plottable series",
            len(rows),
            list(rows[0].keys()),
        )
        return "end"
    return "auto_chart"


def auto_chart_node(state: AskDataState) -> dict:
    """
    Charts a SQL result without the model having to ask for one.

    `route_after_sql` has already established the rows are chartable, so a None
    here means the two disagreed -- return no chart rather than an empty frame.
    """
    rows = state.get("query_results") or []
    title = state.get("chart_title") or "Query Result"
    spec = derive_chart_spec(rows, title=title)
    if spec is None:
        logger.warning("auto_chart_node: rows passed the route guard but derived no spec")
        return {}

    summary = summarize_spec(spec)
    logger.info("auto_chart: rendered %s with %d categories", spec.kind, len(spec.categories))
    return {
        "chart_spec": spec.model_dump(),
        "ui_artifacts": [_chart_artifact(spec, "art_askdata_auto_chart", summary)],
    }


def render_chart_node(state: AskDataState) -> dict:
    """Builds a chart for an explicitly requested chart type."""
    result = generate_visualization(
        ChartGeneratorInput(
            **_supplied(
                chart_type=state["chart_type"],
                title=state.get("chart_title"),
                data=state.get("chart_data") or {},
            )
        )
    )

    if result.chart_spec is None:
        # An explicit chart request whose data held no series is a caller
        # error, not a silent no-op -- surface it so the copilot can say why.
        logger.info("render_chart: %s", result.summary)
        return {"errors": [result.summary]}

    logger.info("render_chart: rendered %s", result.chart_spec.kind)
    return {
        "chart_spec": result.chart_spec.model_dump(),
        "plotly_json": result.plotly_json,
        "ui_artifacts": [_chart_artifact(result.chart_spec, "art_askdata_chart", result.summary)],
    }


def simulate_growth_node(state: AskDataState) -> dict:
    """Runs Monte Carlo simulation to project annual lift."""
    result = simulate_and_visualize_growth(
        GrowthSimulationInput(
            **_supplied(
                baseline_monthly_revenue=state["baseline_monthly_revenue"],
                expected_lift_pct=state.get("expected_lift_pct"),
                lift_std_dev=state.get("lift_std_dev"),
            )
        )
    )
    logger.info("simulate_growth: rendered growth forecast chart")
    return {
        "growth_result": result.forecast.model_dump(),
        "chart_spec": result.chart_spec.model_dump(),
        "plotly_json": result.plotly_json,
        "ui_artifacts": [_chart_artifact(result.chart_spec, "art_growth_forecast", result.summary)],
    }


def report_missing_node(state: AskDataState) -> dict:
    """No branch had its inputs supplied — say which one is needed."""
    return {
        "missing_inputs": [
            "query (for SQL) | chart_type (for a chart) | "
            "baseline_monthly_revenue (for a growth forecast)"
        ]
    }


builder = StateGraph(AskDataState)
builder.add_node("run_sql", run_sql_node)
builder.add_node("auto_chart", auto_chart_node)
builder.add_node("render_chart", render_chart_node)
builder.add_node("simulate_growth", simulate_growth_node)
builder.add_node("report_missing", report_missing_node)

builder.add_conditional_edges(
    START,
    route_request,
    {
        "run_sql": "run_sql",
        "render_chart": "render_chart",
        "simulate_growth": "simulate_growth",
        "report_missing": "report_missing",
    },
)
builder.add_conditional_edges(
    "run_sql",
    route_after_sql,
    {"auto_chart": "auto_chart", "end": END},
)
builder.add_edge("auto_chart", END)
builder.add_edge("render_chart", END)
builder.add_edge("simulate_growth", END)
builder.add_edge("report_missing", END)

askdata_subgraph = builder.compile()
