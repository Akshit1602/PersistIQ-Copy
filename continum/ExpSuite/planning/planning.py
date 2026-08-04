from typing import Optional

import numpy as np
from pydantic import BaseModel, Field
from scipy.stats import norm


class PowerCalcInput(BaseModel):
    baseline_rate: float = Field(
        ..., description="Historical baseline conversion rate or mean (e.g. 0.10 for 10%)"
    )
    mde_relative: float = Field(
        ..., description="Target relative Minimum Detectable Effect (e.g. 0.05 for 5% lift)"
    )
    alpha: float = Field(0.05, description="Significance level (Type I error rate)")
    power: float = Field(0.80, description="Statistical power (1 - Type II error rate)")
    daily_traffic: Optional[int] = Field(
        None, description="Average total daily traffic across all variants"
    )
    num_variants: int = Field(2, description="Total number of variants including Control")


class PowerCalcResult(BaseModel):
    sample_size_per_variant: int
    total_sample_size: int
    mde_absolute: float
    mde_relative: float
    alpha: float
    power: float
    estimated_days: Optional[int]
    summary: str


def calculate_power(input_data: PowerCalcInput) -> PowerCalcResult:
    """
    Computes required sample size per variant and total test duration using two-proportion z-test power formulas.
    """
    p1 = input_data.baseline_rate
    mde_abs = p1 * input_data.mde_relative
    p2 = p1 + mde_abs

    # Pooled variance estimate
    p_avg = (p1 + p2) / 2.0

    # Critical Z-values
    z_alpha = norm.ppf(1.0 - input_data.alpha / 2.0)
    z_beta = norm.ppf(input_data.power)

    # Standard formula for sample size per variant
    numerator = 2 * (z_alpha + z_beta) ** 2 * p_avg * (1.0 - p_avg)
    denominator = (p2 - p1) ** 2

    if denominator <= 0 or p_avg <= 0 or p_avg >= 1:
        n_per_variant = 0
    else:
        n_per_variant = int(np.ceil(numerator / denominator))

    total_n = n_per_variant * input_data.num_variants

    # Estimate test duration in days
    estimated_days = None
    if input_data.daily_traffic and input_data.daily_traffic > 0:
        estimated_days = int(np.ceil(total_n / input_data.daily_traffic))

    duration_str = f"{estimated_days} days" if estimated_days else "N/A (daily traffic unspecified)"

    summary = (
        f"Power Calculation: Required sample size is {n_per_variant:,} per variant "
        f"({total_n:,} total) to detect a {input_data.mde_relative * 100:.2f}% relative lift "
        f"at {input_data.power * 100:.0f}% power and alpha={input_data.alpha}. "
        f"Estimated duration: {duration_str}."
    )

    return PowerCalcResult(
        sample_size_per_variant=n_per_variant,
        total_sample_size=total_n,
        mde_absolute=float(mde_abs),
        mde_relative=input_data.mde_relative,
        alpha=input_data.alpha,
        power=input_data.power,
        estimated_days=estimated_days,
        summary=summary,
    )
