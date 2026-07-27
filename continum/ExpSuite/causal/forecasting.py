from typing import Dict
import numpy as np
from pydantic import BaseModel, Field


class ForecastInput(BaseModel):
    baseline_monthly_revenue: float = Field(..., description="Current baseline monthly revenue in dollars")
    expected_lift_pct: float = Field(..., description="Expected percentage lift, e.g. 0.03 for 3%")
    lift_std_dev: float = Field(0.01, description="Standard deviation / uncertainty of the lift estimate")
    num_simulations: int = Field(10000, description="Number of Monte Carlo simulation draws")


class ForecastResult(BaseModel):
    projected_quarterly_lift: float
    projected_annual_lift: float
    p10_annual_lift: float
    p90_annual_lift: float
    simulation_bounds: Dict[str, float]
    summary: str


def run_monte_carlo_forecast(input_data: ForecastInput) -> ForecastResult:
    """
    Executes a Monte Carlo simulation to project quarterly and annual revenue impact with uncertainty bounds.
    """
    # Draw random lift multipliers from normal distribution
    lift_draws = np.random.normal(
        loc=input_data.expected_lift_pct,
        scale=input_data.lift_std_dev,
        size=input_data.num_simulations
    )

    monthly_base = input_data.baseline_monthly_revenue
    annual_base = monthly_base * 12.0

    annual_incremental_draws = annual_base * lift_draws
    quarterly_incremental_draws = (monthly_base * 3.0) * lift_draws

    mean_annual = float(np.mean(annual_incremental_draws))
    mean_quarterly = float(np.mean(quarterly_incremental_draws))

    p10 = float(np.percentile(annual_incremental_draws, 10))
    p50 = float(np.percentile(annual_incremental_draws, 50))
    p90 = float(np.percentile(annual_incremental_draws, 90))

    summary = (
        f"Monte Carlo Growth Forecast (+{input_data.expected_lift_pct * 100:.1f}% ± {input_data.lift_std_dev * 100:.1f}%): "
        f"Expected Annual Lift: +${mean_annual:,.2f} (P10: +${p10:,.2f}, P90: +${p90:,.2f}). "
        f"Expected Quarterly Lift: +${mean_quarterly:,.2f}."
    )

    return ForecastResult(
        projected_quarterly_lift=mean_quarterly,
        projected_annual_lift=mean_annual,
        p10_annual_lift=p10,
        p90_annual_lift=p90,
        simulation_bounds={"p10": p10, "p50": p50, "p90": p90},
        summary=summary
    )