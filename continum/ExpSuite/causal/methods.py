import numpy as np
from pydantic import BaseModel, Field
from scipy.stats import norm


class DiDInput(BaseModel):
    control_pre: float = Field(..., description="Mean metric value for Control in pre-period")
    control_post: float = Field(..., description="Mean metric value for Control in post-period")
    treatment_pre: float = Field(..., description="Mean metric value for Treatment in pre-period")
    treatment_post: float = Field(..., description="Mean metric value for Treatment in post-period")
    std_error: float = Field(0.01, description="Estimated standard error of the double difference")


class DiDResult(BaseModel):
    control_diff: float
    treatment_diff: float
    did_effect: float
    relative_effect_pct: float
    z_stat: float
    p_value: float
    is_significant: bool
    summary: str


def calculate_diff_in_diff(input_data: DiDInput) -> DiDResult:
    """
    Computes Difference-in-Differences (DiD) treatment effect for observational rollouts.
    Formula: DiD = (Y_treatment_post - Y_treatment_pre) - (Y_control_post - Y_control_pre)
    """
    ctrl_diff = input_data.control_post - input_data.control_pre
    trt_diff = input_data.treatment_post - input_data.treatment_pre
    did_effect = trt_diff - ctrl_diff

    rel_effect = (did_effect / input_data.control_post) * 100.0 if input_data.control_post != 0 else 0.0

    se = input_data.std_error if input_data.std_error > 0 else 1e-6
    z_stat = did_effect / se
    p_val = 2 * (1 - norm.cdf(abs(z_stat)))
    is_sig = p_val < 0.05

    summary = (
        f"Difference-in-Differences Analysis: Effect = {did_effect:.4f} ({rel_effect:+.2f}% relative lift). "
        f"p-value = {p_val:.5f}. Status: {'Statistically Significant' if is_sig else 'Not Statistically Significant'}."
    )

    return DiDResult(
        control_diff=float(ctrl_diff),
        treatment_diff=float(trt_diff),
        did_effect=float(did_effect),
        relative_effect_pct=float(rel_effect),
        z_stat=float(z_stat),
        p_value=float(p_val),
        is_significant=is_sig,
        summary=summary
    )