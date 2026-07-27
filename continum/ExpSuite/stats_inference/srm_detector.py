from typing import List, Optional
from pydantic import BaseModel, Field
from scipy.stats import chisquare


class SRMInput(BaseModel):
    observed_counts: List[int] = Field(..., description="Observed sample counts per variant, e.g. [control, treatment]")
    expected_ratios: Optional[List[float]] = Field(None, description="Expected allocation ratios, defaults to equal splits e.g. [0.5, 0.5]")
    alpha: float = Field(0.01, description="Significance threshold for flagging SRM")


class SRMResult(BaseModel):
    chi2_stat: float
    p_value: float
    has_srm: bool
    severity: str  # "NONE", "WARNING", "CRITICAL"
    observed_counts: List[int]
    expected_counts: List[float]
    summary: str


def detect_srm(input_data: SRMInput) -> SRMResult:
    """
    Executes Chi-Square Goodness-of-Fit test to detect Sample Ratio Mismatch (SRM).
    """
    total_count = sum(input_data.observed_counts)
    num_variants = len(input_data.observed_counts)
    
    if input_data.expected_ratios is None:
        expected_ratios = [1.0 / num_variants] * num_variants
    else:
        expected_ratios = input_data.expected_ratios

    expected_counts = [total_count * ratio for ratio in expected_ratios]
    
    chi2_stat, p_val = chisquare(f_obs=input_data.observed_counts, f_exp=expected_counts)
    
    has_srm = float(p_val) < input_data.alpha
    if p_val < 0.0001:
        severity = "CRITICAL"
    elif p_val < input_data.alpha:
        severity = "WARNING"
    else:
        severity = "NONE"

    summary = (
        f"SRM Analysis: Chi2 = {chi2_stat:.4f}, p-value = {p_val:.5f}. "
        f"Status: {severity}. {'Sample Ratio Mismatch detected!' if has_srm else 'Traffic distribution is balanced.'}"
    )

    return SRMResult(
        chi2_stat=float(chi2_stat),
        p_value=float(p_val),
        has_srm=has_srm,
        severity=severity,
        observed_counts=input_data.observed_counts,
        expected_counts=[float(c) for c in expected_counts],
        summary=summary
    )