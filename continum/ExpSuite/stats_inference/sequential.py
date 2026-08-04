import numpy as np
from pydantic import BaseModel, Field


class SequentialInput(BaseModel):
    control_successes: int
    control_count: int
    treatment_successes: int
    treatment_count: int
    alpha: float = Field(0.05, description="Type I error rate")
    beta: float = Field(0.20, description="Type II error rate")


class SequentialResult(BaseModel):
    sprt_stat: float
    upper_bound: float
    lower_bound: float
    decision: str  # "STOP_SUCCESS", "STOP_FUTILITY", "CONTINUE"
    summary: str


def run_sprt(input_data: SequentialInput) -> SequentialResult:
    """
    Executes Wald's Sequential Probability Ratio Test (SPRT) for early stopping.
    """
    a = input_data.alpha
    b = input_data.beta

    # Wald boundaries
    lower_bound = np.log(b / (1.0 - a))
    upper_bound = np.log((1.0 - b) / a)

    p_ctrl = (
        input_data.control_successes / input_data.control_count
        if input_data.control_count > 0
        else 0.5
    )
    p_trt = (
        input_data.treatment_successes / input_data.treatment_count
        if input_data.treatment_count > 0
        else 0.5
    )

    # Log likelihood ratio approximation
    e_ctrl = input_data.control_count * p_ctrl
    e_trt = input_data.treatment_count * p_trt

    # Standardized SPRT log-ratio statistic
    diff = p_trt - p_ctrl
    se = np.sqrt(
        (p_ctrl * (1 - p_ctrl) / max(1, input_data.control_count))
        + (p_trt * (1 - p_trt) / max(1, input_data.treatment_count))
    )

    sprt_stat = float(diff / se) if se > 0 else 0.0

    if sprt_stat >= upper_bound:
        decision = "STOP_SUCCESS"
        summary = f"SPRT Boundary Crossed (Upper={upper_bound:.2f}). Experiment can stop early for SUCCESS."
    elif sprt_stat <= lower_bound:
        decision = "STOP_FUTILITY"
        summary = f"SPRT Boundary Crossed (Lower={lower_bound:.2f}). Experiment can stop early for FUTILITY."
    else:
        decision = "CONTINUE"
        summary = f"SPRT stat ({sprt_stat:.2f}) within bounds [{lower_bound:.2f}, {upper_bound:.2f}]. Continue testing."

    return SequentialResult(
        sprt_stat=sprt_stat,
        upper_bound=float(upper_bound),
        lower_bound=float(lower_bound),
        decision=decision,
        summary=summary,
    )
