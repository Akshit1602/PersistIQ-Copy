import json
from typing import Any, Dict, List, Optional

import plotly.express as px
import plotly.graph_objects as go
from pydantic import BaseModel, Field


class ChartGeneratorInput(BaseModel):
    chart_type: str = Field(
        ...,
        description="Type of chart: 'metric_lift', 'srm_distribution', 'p_value_trend', 'growth_forecast'",
    )
    title: str = Field("Experiment Visualization", description="Chart title")
    data: Dict[str, Any] = Field(..., description="Data required for the specified chart type")


class ChartGeneratorResult(BaseModel):
    chart_type: str
    plotly_json: Dict[str, Any]
    summary: str


def build_metric_lift_chart(
    control_mean: float,
    treatment_mean: float,
    ci_lower: Optional[float] = None,
    ci_upper: Optional[float] = None,
    metric_name: str = "Metric",
    title: str = "Control vs. Treatment Comparison",
) -> Dict[str, Any]:
    """
    Renders a bar chart comparing Control and Treatment with optional confidence interval error bars.
    """
    categories = ["Control", "Treatment"]
    means = [control_mean, treatment_mean]

    error_y = None
    if ci_lower is not None and ci_upper is not None:
        # Treatment error bar relative calculation
        error_val = (ci_upper - ci_lower) / 2.0
        error_y = dict(type="data", array=[0, error_val], visible=True)

    fig = go.Figure(
        data=[
            go.Bar(
                x=categories,
                y=means,
                marker_color=["#636EFA", "#00CC96"],
                error_y=error_y,
                text=[f"{m:.4f}" for m in means],
                textposition="auto",
            )
        ]
    )

    fig.update_layout(
        title=title,
        yaxis_title=metric_name,
        template="plotly_white",
        margin=dict(l=40, r=40, t=60, b=40),
    )

    return json.loads(fig.to_json())


def build_srm_distribution_chart(
    observed_counts: List[int],
    expected_counts: List[float],
    variant_names: Optional[List[str]] = None,
    title: str = "Sample Ratio Allocation (SRM Check)",
) -> Dict[str, Any]:
    """
    Renders a grouped bar chart comparing observed vs expected traffic counts per variant.
    """
    num_variants = len(observed_counts)
    names = variant_names or ["Control"] + [f"Treatment_{i}" for i in range(1, num_variants)]

    fig = go.Figure(
        data=[
            go.Bar(name="Observed", x=names, y=observed_counts, marker_color="#19D3F3"),
            go.Bar(name="Expected", x=names, y=expected_counts, marker_color="#FF6692"),
        ]
    )

    fig.update_layout(
        title=title,
        barmode="group",
        yaxis_title="User Count",
        template="plotly_white",
        margin=dict(l=40, r=40, t=60, b=40),
    )

    return json.loads(fig.to_json())


def build_growth_forecast_chart(
    p10_annual: float,
    p50_annual: float,
    p90_annual: float,
    title: str = "Projected Annual Revenue Lift Distribution",
) -> Dict[str, Any]:
    """
    Renders a horizon bar/range chart showing P10, P50, and P90 growth projections.
    """
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=["P10 (Pessimistic)", "P50 (Expected)", "P90 (Optimistic)"],
            y=[p10_annual, p50_annual, p90_annual],
            marker_color=["#FFA15A", "#00CC96", "#AB63FA"],
            text=[f"${v:,.2f}" for v in [p10_annual, p50_annual, p90_annual]],
            textposition="auto",
        )
    )

    fig.update_layout(
        title=title,
        yaxis_title="Annual Revenue Lift ($)",
        template="plotly_white",
        margin=dict(l=40, r=40, t=60, b=40),
    )

    return json.loads(fig.to_json())


def generate_visualization(input_data: ChartGeneratorInput) -> ChartGeneratorResult:
    """
    Master dispatcher for generating Plotly JSON visualizations based on chart type.
    """
    c_type = input_data.chart_type
    d = input_data.data

    if c_type == "metric_lift":
        fig_json = build_metric_lift_chart(
            control_mean=d.get("control_mean", 0.0),
            treatment_mean=d.get("treatment_mean", 0.0),
            ci_lower=d.get("ci_lower"),
            ci_upper=d.get("ci_upper"),
            metric_name=d.get("metric_name", "Value"),
            title=input_data.title,
        )
    elif c_type == "srm_distribution":
        fig_json = build_srm_distribution_chart(
            observed_counts=d.get("observed_counts", []),
            expected_counts=d.get("expected_counts", []),
            variant_names=d.get("variant_names"),
            title=input_data.title,
        )
    elif c_type == "growth_forecast":
        fig_json = build_growth_forecast_chart(
            p10_annual=d.get("p10", 0.0),
            p50_annual=d.get("p50", 0.0),
            p90_annual=d.get("p90", 0.0),
            title=input_data.title,
        )
    else:
        # Default simple bar chart
        fig = px.bar(x=["Control", "Treatment"], y=[0, 0], title=input_data.title)
        fig_json = json.loads(fig.to_json())

    return ChartGeneratorResult(
        chart_type=c_type,
        plotly_json=fig_json,
        summary=f"Successfully generated Plotly JSON for '{c_type}' visual.",
    )
