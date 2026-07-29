import numpy as np
from pydantic import BaseModel, Field
from scipy.stats import norm


class StatTestInput(BaseModel):
    control_mean: float = Field(..., description="Control sample mean")
    control_std: float = Field(..., description="Control sample standard deviation")
    control_count: int = Field(..., description="Control sample count")
    treatment_mean: float = Field(..., description="Treatment sample mean")
    treatment_std: float = Field(..., description="Treatment sample standard deviation")
    treatment_count: int = Field(..., description="Treatment sample count")
    alpha: float = Field(0.05, description="Significance level")


class StatTestResult(BaseModel):
    absolute_lift: float
    relative_lift: float
    std_error: float
    z_stat: float
    p_value: float
    ci_lower: float
    ci_upper: float
    is_stat_sig: bool
    summary: str


def calculate_hypothesis_test(input_data: StatTestInput) -> StatTestResult:
    """
    Computes Welch's T-Test / Two-Sample Z-Test, confidence intervals, and relative lift.
    """
    c_m, c_s, c_n = input_data.control_mean, input_data.control_std, input_data.control_count
    t_m, t_s, t_n = input_data.treatment_mean, input_data.treatment_std, input_data.treatment_count

    abs_lift = t_m - c_m
    rel_lift = (abs_lift / c_m) if c_m != 0 else 0.0

    # Standard error of difference between means
    se = np.sqrt((c_s**2 / c_n) + (t_s**2 / t_n))
    z_stat = abs_lift / se if se > 0 else 0.0

    # Two-tailed p-value
    p_value = 2 * (1 - norm.cdf(abs(z_stat)))

    # Confidence Interval
    z_critical = norm.ppf(1 - input_data.alpha / 2)
    ci_lower = abs_lift - z_critical * se
    ci_upper = abs_lift + z_critical * se

    is_sig = p_value < input_data.alpha

    summary = (
        f"Hypothesis Test Results: Relative Lift = {rel_lift * 100:.2f}%, "
        f"p-value = {p_value:.5f}, 95% CI = [{ci_lower:.4f}, {ci_upper:.4f}]. "
        f"Result is {'Statistically Significant' if is_sig else 'Not Statistically Significant'}."
    )

    return StatTestResult(
        absolute_lift=float(abs_lift),
        relative_lift=float(rel_lift),
        std_error=float(se),
        z_stat=float(z_stat),
        p_value=float(p_value),
        ci_lower=float(ci_lower),
        ci_upper=float(ci_upper),
        is_stat_sig=is_sig,
        summary=summary,
    )
