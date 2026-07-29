from pydantic import BaseModel, Field


class OpportunitySizingInput(BaseModel):
    annual_traffic: int = Field(..., description="Annual exposed user volume")
    baseline_conversion_rate: float = Field(
        ..., description="Current baseline conversion rate (0.0 to 1.0)"
    )
    average_order_value: float = Field(..., description="Average Order Value (AOV) in dollars")
    assumed_relative_lift: float = Field(0.02, description="Target assumed lift e.g. 0.02 for +2%")


class OpportunitySizingResult(BaseModel):
    baseline_conversions: int
    baseline_annual_revenue: float
    incremental_conversions: int
    incremental_annual_revenue: float
    incremental_quarterly_revenue: float
    summary: str


def calculate_opportunity_size(input_data: OpportunitySizingInput) -> OpportunitySizingResult:
    """
    Computes baseline revenue and potential incremental conversions/revenue from a target hypothesis.
    """
    baseline_convs = int(input_data.annual_traffic * input_data.baseline_conversion_rate)
    baseline_rev = baseline_convs * input_data.average_order_value

    new_conv_rate = input_data.baseline_conversion_rate * (1.0 + input_data.assumed_relative_lift)
    new_convs = int(input_data.annual_traffic * new_conv_rate)

    incremental_convs = new_convs - baseline_convs
    incremental_annual_rev = incremental_convs * input_data.average_order_value
    incremental_quarterly_rev = incremental_annual_rev / 4.0

    summary = (
        f"Opportunity Sizing (+{input_data.assumed_relative_lift * 100:.2f}% lift target): "
        f"Projected +{incremental_convs:,} incremental orders/year, driving "
        f"+${incremental_annual_rev:,.2f} annual revenue (+${incremental_quarterly_rev:,.2f}/quarter)."
    )

    return OpportunitySizingResult(
        baseline_conversions=baseline_convs,
        baseline_annual_revenue=float(baseline_rev),
        incremental_conversions=incremental_convs,
        incremental_annual_revenue=float(incremental_annual_rev),
        incremental_quarterly_revenue=float(incremental_quarterly_rev),
        summary=summary,
    )
