from pydantic import BaseModel, Field

from continum.AskData.chart_spec import ChartSpec, spec_to_plotly
from continum.AskData.visual_generator import build_growth_forecast_spec
from continum.ExpSuite.causal.forecasting import (
    ForecastInput,
    ForecastResult,
    run_monte_carlo_forecast,
)


class GrowthSimulationInput(BaseModel):
    baseline_monthly_revenue: float = Field(
        ..., description="Current baseline monthly revenue in dollars"
    )
    expected_lift_pct: float = Field(
        ..., description="Target expected percentage lift e.g. 0.02 for 2%"
    )
    lift_std_dev: float = Field(0.01, description="Standard deviation / uncertainty of the lift")


class GrowthSimulationResult(BaseModel):
    forecast: ForecastResult
    # The renderer-neutral chart the UI draws. `plotly_json` is derived from it
    # and kept for exports; nothing in MatchView reads it.
    chart_spec: ChartSpec
    plotly_json: dict
    summary: str


def simulate_and_visualize_growth(input_data: GrowthSimulationInput) -> GrowthSimulationResult:
    """
    Runs Monte Carlo simulation and constructs a corresponding Plotly chart payload.
    """
    f_input = ForecastInput(
        baseline_monthly_revenue=input_data.baseline_monthly_revenue,
        expected_lift_pct=input_data.expected_lift_pct,
        lift_std_dev=input_data.lift_std_dev,
    )

    forecast_res = run_monte_carlo_forecast(f_input)

    spec = build_growth_forecast_spec(
        p10_annual=forecast_res.p10_annual_lift,
        p50_annual=forecast_res.projected_annual_lift,
        p90_annual=forecast_res.p90_annual_lift,
        title=f"Annual Growth Projection (+{input_data.expected_lift_pct * 100:.1f}% Lift)",
    )

    return GrowthSimulationResult(
        forecast=forecast_res,
        chart_spec=spec,
        plotly_json=spec_to_plotly(spec),
        summary=forecast_res.summary,
    )
