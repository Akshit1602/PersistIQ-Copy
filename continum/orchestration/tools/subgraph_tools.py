"""
Domain subgraphs exposed as agent tools.

Every parameter below is required by the ExpSuite/mapMeta/AskData function it
ultimately reaches. They are declared on the tool signature rather than defaulted
inside a node so the model must obtain them from the conversation — and, when it
cannot, ask the user. `supervisor.py`'s prompt is explicit about this: "If
required parameters are missing, ask for exactly those parameters. Never fill
them with assumed or illustrative values."

Each wrapper returns whatever the subgraph put in state, plus a `missing_inputs`
list when a node could not run. The supervisor turns a non-empty `missing_inputs`
into a clarification request instead of a result.
"""

from typing import List, Optional

from langchain_core.tools import tool

from continum.orchestration.subgraphs import (
    analysis_subgraph,
    askdata_subgraph,
    ingestion_subgraph,
    monitoring_subgraph,
    planning_subgraph,
)

# Plotly figure JSON runs to several kilobytes of layout per chart. It reaches
# the frontend as part of no artifact (the UI renders `chart_spec`), so leaving
# it on the tool return would only burn LLM context -- LangChain serialises the
# whole dict into the ToolMessage the model reads next turn.
_MODEL_INVISIBLE_KEYS = ("plotly_json",)


def _finalize(result: dict) -> dict:
    """
    Normalizes a subgraph result for the agent:

    * de-duplicates `missing_inputs` (the `operator.add` reducer concatenates one
      entry per node that was blocked, so the same field can appear several
      times) while preserving order;
    * dumps `ui_artifacts` to plain dicts, because LangChain JSON-encodes the
      tool return and a pydantic model in it forces a `str()` fallback that the
      SSE layer cannot parse -- which silently drops the card;
    * strips payloads that only bloat the model's context.
    """
    missing = result.get("missing_inputs") or []
    if missing:
        result["missing_inputs"] = list(dict.fromkeys(missing))

    artifacts = result.get("ui_artifacts")
    if artifacts:
        result["ui_artifacts"] = [
            artifact.model_dump() if hasattr(artifact, "model_dump") else artifact
            for artifact in artifacts
        ]

    for key in _MODEL_INVISIBLE_KEYS:
        result.pop(key, None)
    return result


@tool("run_ingestion_workflow")
def run_ingestion_workflow() -> dict:
    """Scan the database schema and catalog existing experiments found in it."""
    return _finalize(
        ingestion_subgraph.invoke({"messages": [], "raw_tables_discovered": [], "errors": []})
    )


@tool("run_experiment_planning_workflow")
def run_experiment_planning_workflow(
    hypothesis: str,
    primary_metric: str,
    baseline_rate: float,
    mde_relative: float,
    annual_traffic: int,
    average_order_value: float,
    retail_domain: Optional[str] = None,
    daily_traffic: Optional[int] = None,
    num_variants: Optional[int] = None,
    control_split: Optional[float] = None,
    assumed_relative_lift: Optional[float] = None,
    experiment_id: Optional[str] = None,
) -> dict:
    """
    Generate an experiment brief: metric plan, opportunity sizing, power/sample
    size, and traffic split. Requires the hypothesis, the primary metric name,
    the historical baseline rate (0-1), the target relative MDE (e.g. 0.05 for
    5%), annual exposed traffic, and average order value. Ask the user for any
    of these you do not have — do not guess them.
    """
    return _finalize(
        planning_subgraph.invoke(
            {
                "messages": [{"role": "user", "content": hypothesis}],
                "active_experiment_id": experiment_id,
                "primary_metric": primary_metric,
                "retail_domain": retail_domain,
                "baseline_rate": baseline_rate,
                "mde_relative": mde_relative,
                "annual_traffic": annual_traffic,
                "average_order_value": average_order_value,
                "assumed_relative_lift": assumed_relative_lift,
                "daily_traffic": daily_traffic,
                "num_variants": num_variants,
                "control_split": control_split,
                "missing_inputs": [],
                "ui_artifacts": [],
                "errors": [],
            }
        )
    )


@tool("run_health_monitoring_workflow")
def run_health_monitoring_workflow(
    experiment_id: str,
    observed_counts: Optional[List[int]] = None,
    expected_ratios: Optional[List[float]] = None,
) -> dict:
    """
    Fetch StatSig pulse telemetry and run a Sample Ratio Mismatch check. Pass
    observed_counts as [control, treatment] when you have measured exposure
    counts; otherwise the counts reported by telemetry are used. Note that
    telemetry falls back to labelled mock data when STATSIG_API_KEY is unset,
    and that is reported in guardrail_alerts.
    """
    return _finalize(
        monitoring_subgraph.invoke(
            {
                "messages": [],
                "active_experiment_id": experiment_id,
                "observed_counts": observed_counts,
                "expected_ratios": expected_ratios,
                "srm_status": "HEALTHY",
                "guardrail_alerts": [],
                "missing_inputs": [],
                "ui_artifacts": [],
                "errors": [],
            }
        )
    )


@tool("run_experiment_analysis_workflow")
def run_experiment_analysis_workflow(
    experiment_id: str,
    control_mean: float,
    control_std: float,
    control_count: int,
    treatment_mean: float,
    treatment_std: float,
    treatment_count: int,
    primary_metric: Optional[str] = None,
    alpha: Optional[float] = None,
    use_cuped: bool = False,
    y_control: Optional[List[float]] = None,
    x_control: Optional[List[float]] = None,
    y_treatment: Optional[List[float]] = None,
    x_treatment: Optional[List[float]] = None,
    control_pre: Optional[float] = None,
    control_post: Optional[float] = None,
    treatment_pre: Optional[float] = None,
    treatment_post: Optional[float] = None,
) -> dict:
    """
    Run the full analysis pass: optional CUPED variance reduction, hypothesis
    test, optional Difference-in-Differences, ROI framing, and a metric-lift
    chart. Requires observed means, standard deviations, and counts for both
    arms. Set use_cuped only when you also pass the four pre-period covariate
    arrays. Pass the four pre/post means only when a DiD estimate is wanted.
    """
    return _finalize(
        analysis_subgraph.invoke(
            {
                "messages": [],
                "active_experiment_id": experiment_id,
                "primary_metric": primary_metric or "",
                "use_cuped": use_cuped,
                "control_mean": control_mean,
                "control_std": control_std,
                "control_count": control_count,
                "treatment_mean": treatment_mean,
                "treatment_std": treatment_std,
                "treatment_count": treatment_count,
                "alpha": alpha,
                "y_control": y_control,
                "x_control": x_control,
                "y_treatment": y_treatment,
                "x_treatment": x_treatment,
                "control_pre": control_pre,
                "control_post": control_post,
                "treatment_pre": treatment_pre,
                "treatment_post": treatment_post,
                "missing_inputs": [],
                "ui_artifacts": [],
                "errors": [],
            }
        )
    )


def _askdata(**fields) -> dict:
    base = {"messages": [], "missing_inputs": [], "ui_artifacts": [], "errors": []}
    return _finalize(askdata_subgraph.invoke({**base, **fields}))


@tool("ask_data_sql")
def ask_data_sql(query: str, chart_title: Optional[str] = None, visualize: bool = True) -> dict:
    """
    Execute a read-only SQL query against the configured warehouse and return the
    rows. Only SELECT and WITH statements are permitted; anything else is
    rejected. Results are returned as rows, so state figures from them verbatim.

    A chart is generated automatically whenever the rows are chartable, and is
    rendered by the UI — describe the finding in words and do not attempt to
    draw it. Pass chart_title to label it. Set visualize=False only when the
    user explicitly asked for numbers without a chart.
    """
    return _askdata(query=query, chart_title=chart_title, visualize=visualize)


@tool("ask_data_visualize")
def ask_data_visualize(chart_type: str, data: dict, title: Optional[str] = None) -> dict:
    """
    Build a chart the MatchView UI renders as a card. Call this whenever the user
    asks to see, plot, chart, graph, compare, or break down anything, and
    whenever a comparison across categories or over time would land better as a
    picture than as prose.

    chart_type is either a named experiment chart or a generic shape:

    * 'metric_lift' — data: control_mean, treatment_mean, optional
      ci_lower/ci_upper, metric_name.
    * 'srm_distribution' — data: observed_counts, expected_counts, optional
      variant_names.
    * 'growth_forecast' — data: p10, p50, p90.
    * 'bar' | 'grouped_bar' | 'line' | 'area' | 'pie' | 'scatter' — data:
      either {"categories": [...], "series": [{"name": ..., "values": [...]}]}
      (or the shorthand {"categories": [...], "values": [...]}), or
      {"rows": [ {...}, ... ]} to chart query rows directly. Optional
      x_title, y_title, and value_format ('number' | 'currency' | 'percent').
    * 'auto' — infer the shape from {"rows": [...]}.

    Every number must come from a tool result already in this conversation.
    Never pass illustrative or assumed values just to produce a picture.
    """
    return _askdata(chart_type=chart_type, chart_data=data, chart_title=title)


@tool("ask_data_insights")
def ask_data_insights(
    baseline_monthly_revenue: float,
    expected_lift_pct: float,
    lift_std_dev: Optional[float] = None,
) -> dict:
    """
    Run a Monte Carlo growth forecast and return projected quarterly/annual lift
    with P10/P50/P90 bounds, plus a chart. Requires current baseline monthly
    revenue and the expected relative lift (e.g. 0.02 for 2%).
    """
    return _askdata(
        baseline_monthly_revenue=baseline_monthly_revenue,
        expected_lift_pct=expected_lift_pct,
        lift_std_dev=lift_std_dev,
    )


subgraph_tools = [
    run_ingestion_workflow,
    run_experiment_planning_workflow,
    run_health_monitoring_workflow,
    run_experiment_analysis_workflow,
    ask_data_sql,
    ask_data_visualize,
    ask_data_insights,
]
