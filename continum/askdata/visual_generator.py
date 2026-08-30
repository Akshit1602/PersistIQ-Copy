"""
Chart construction for the copilot.

Every builder here produces a `ChartSpec` -- the renderer-neutral form the
MatchView frontend draws -- and Plotly JSON is derived from that one spec rather
than hand-assembled per chart type. Previously each builder wrote its own
`go.Figure`, so the frontend had nothing to render but a Plotly blob it has no
library for, and the three hard-coded chart types were the only shapes the
copilot could ever produce. `generate_visualization` now also accepts the
generic kinds (bar/line/pie/...) and raw result rows, which is what lets an
arbitrary question get a chart.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from continum.askdata.chart_spec import (
    SERIES_COLORS,
    ChartSeries,
    ChartSpec,
    derive_chart_spec,
    spec_to_plotly,
    summarize_spec,
)

# Named chart types carry domain semantics (which arm is which, what the error
# bar means); generic kinds are shape-only and take their meaning from `data`.
NAMED_CHART_TYPES = ("metric_lift", "srm_distribution", "growth_forecast")
GENERIC_CHART_KINDS = ("bar", "grouped_bar", "line", "area", "pie", "scatter")
SUPPORTED_CHART_TYPES = NAMED_CHART_TYPES + GENERIC_CHART_KINDS + ("auto",)


class ChartGeneratorInput(BaseModel):
    chart_type: str = Field(
        "auto",
        description=(
            "One of: 'auto' (infer from rows), 'metric_lift', 'srm_distribution', "
            "'growth_forecast', 'bar', 'grouped_bar', 'line', 'area', 'pie', 'scatter'"
        ),
    )
    title: str = Field("Experiment Visualization", description="Chart title")
    data: Dict[str, Any] = Field(
        default_factory=dict, description="Data required for the specified chart type"
    )


class ChartGeneratorResult(BaseModel):
    chart_type: str
    # The renderer-neutral spec the UI draws. None when the supplied data held
    # nothing plottable -- callers must fall back to text rather than render an
    # empty axis.
    chart_spec: Optional[ChartSpec] = None
    plotly_json: Dict[str, Any] = Field(default_factory=dict)
    summary: str


def build_metric_lift_spec(
    control_mean: float,
    treatment_mean: float,
    ci_lower: Optional[float] = None,
    ci_upper: Optional[float] = None,
    metric_name: str = "Metric",
    title: str = "Control vs. Treatment Comparison",
) -> ChartSpec:
    """
    Control against treatment, with the confidence interval drawn as an error
    bar on the treatment arm only -- the interval is on the estimated effect,
    and putting it on the control baseline would misstate what was measured.
    """
    error: Optional[List[Optional[float]]] = None
    if ci_lower is not None and ci_upper is not None:
        error = [None, (ci_upper - ci_lower) / 2.0]

    return ChartSpec(
        kind="bar",
        title=title,
        categories=["Control", "Treatment"],
        series=[
            ChartSeries(
                name=metric_name,
                values=[control_mean, treatment_mean],
                color=SERIES_COLORS[0],
                error=error,
            )
        ],
        y_title=metric_name,
        notes=(
            ["Error bar shows the confidence interval on the treatment estimate."] if error else []
        ),
    )


def build_srm_distribution_spec(
    observed_counts: List[int],
    expected_counts: List[float],
    variant_names: Optional[List[str]] = None,
    title: str = "Sample Ratio Allocation (SRM Check)",
) -> ChartSpec:
    """Observed against expected exposure per variant, grouped side by side."""
    num_variants = max(len(observed_counts), len(expected_counts))
    names = variant_names or ["Control"] + [f"Treatment_{i}" for i in range(1, num_variants)]

    return ChartSpec(
        kind="grouped_bar",
        title=title,
        categories=list(names[:num_variants]),
        series=[
            ChartSeries(
                name="Observed",
                values=[float(c) for c in observed_counts],
                color=SERIES_COLORS[0],
            ),
            ChartSeries(
                name="Expected",
                values=[float(c) for c in expected_counts],
                color=SERIES_COLORS[1],
            ),
        ],
        y_title="User Count",
    )


def build_growth_forecast_spec(
    p10_annual: float,
    p50_annual: float,
    p90_annual: float,
    title: str = "Projected Annual Revenue Lift Distribution",
) -> ChartSpec:
    """The three simulated percentiles as a range, lowest to highest."""
    return ChartSpec(
        kind="bar",
        title=title,
        categories=["P10 (Pessimistic)", "P50 (Expected)", "P90 (Optimistic)"],
        series=[
            ChartSeries(
                name="Annual Revenue Lift",
                values=[p10_annual, p50_annual, p90_annual],
                color=SERIES_COLORS[1],
            )
        ],
        y_title="Annual Revenue Lift ($)",
        value_format="currency",
    )


def build_generic_spec(kind: str, title: str, data: Dict[str, Any]) -> Optional[ChartSpec]:
    """
    Builds a shape-only chart from either explicit categories/series or raw
    result rows. Returns None when neither form carries plottable numbers, so
    the caller reports "no chart" rather than rendering an empty frame.
    """
    rows = data.get("rows")
    if rows:
        return derive_chart_spec(
            rows,
            columns=data.get("columns"),
            title=title,
            preferred_kind=kind if kind in GENERIC_CHART_KINDS else None,
        )

    categories = [str(c) for c in (data.get("categories") or data.get("x") or [])]
    raw_series = data.get("series") or []

    # Accept the one-series shorthand `{"categories": [...], "values": [...]}`.
    if not raw_series and data.get("values"):
        raw_series = [{"name": data.get("series_name") or "Value", "values": data["values"]}]

    series: List[ChartSeries] = []
    for index, entry in enumerate(raw_series):
        if isinstance(entry, dict):
            values = entry.get("values") or []
            name = str(entry.get("name") or f"Series {index + 1}")
            error = entry.get("error")
        else:
            values, name, error = list(entry), f"Series {index + 1}", None
        numeric = [None if v is None else float(v) for v in values]
        if not any(v is not None for v in numeric):
            continue
        series.append(
            ChartSeries(
                name=name,
                values=numeric,
                color=SERIES_COLORS[index % len(SERIES_COLORS)],
                error=error,
            )
        )

    if not categories or not series:
        return None

    return ChartSpec(
        kind=kind if kind in GENERIC_CHART_KINDS else ("grouped_bar" if len(series) > 1 else "bar"),
        title=title,
        categories=categories,
        series=series,
        x_title=str(data.get("x_title") or ""),
        y_title=str(data.get("y_title") or ""),
        value_format=data.get("value_format") or "number",
    )


def build_chart_spec(input_data: ChartGeneratorInput) -> Optional[ChartSpec]:
    """Dispatches to the builder for `chart_type`. None when nothing is plottable."""
    chart_type = (input_data.chart_type or "auto").strip().lower()
    data = input_data.data or {}

    if chart_type == "metric_lift":
        return build_metric_lift_spec(
            control_mean=float(data.get("control_mean", 0.0)),
            treatment_mean=float(data.get("treatment_mean", 0.0)),
            ci_lower=data.get("ci_lower"),
            ci_upper=data.get("ci_upper"),
            metric_name=data.get("metric_name", "Value"),
            title=input_data.title,
        )
    if chart_type == "srm_distribution":
        return build_srm_distribution_spec(
            observed_counts=data.get("observed_counts", []),
            expected_counts=data.get("expected_counts", []),
            variant_names=data.get("variant_names"),
            title=input_data.title,
        )
    if chart_type == "growth_forecast":
        return build_growth_forecast_spec(
            p10_annual=float(data.get("p10", 0.0)),
            p50_annual=float(data.get("p50", 0.0)),
            p90_annual=float(data.get("p90", 0.0)),
            title=input_data.title,
        )
    if chart_type == "auto":
        return build_generic_spec("", input_data.title, data)
    return build_generic_spec(chart_type, input_data.title, data)


def generate_visualization(input_data: ChartGeneratorInput) -> ChartGeneratorResult:
    """
    Master dispatcher. An unplottable request returns a result with no spec and
    a summary saying so -- never a placeholder chart of zeroes, which is what
    the old default branch produced and which reads downstream as real data.
    """
    spec = build_chart_spec(input_data)

    if spec is None:
        return ChartGeneratorResult(
            chart_type=input_data.chart_type,
            chart_spec=None,
            plotly_json={},
            summary=(
                f"No chart was generated for '{input_data.chart_type}': the supplied "
                "data contained no numeric series to plot."
            ),
        )

    return ChartGeneratorResult(
        chart_type=spec.kind if input_data.chart_type in ("auto", "") else input_data.chart_type,
        chart_spec=spec,
        plotly_json=spec_to_plotly(spec),
        summary=summarize_spec(spec),
    )


# Backwards-compatible Plotly-returning wrappers. The subgraphs build specs
# directly; these remain for callers importing the original names.


def build_metric_lift_chart(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    return spec_to_plotly(build_metric_lift_spec(*args, **kwargs))


def build_srm_distribution_chart(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    return spec_to_plotly(build_srm_distribution_spec(*args, **kwargs))


def build_growth_forecast_chart(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    return spec_to_plotly(build_growth_forecast_spec(*args, **kwargs))
