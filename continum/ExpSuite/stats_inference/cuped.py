import numpy as np
from pydantic import BaseModel, Field


class CUPEDInput(BaseModel):
    y_control: list[float] = Field(..., description="Post-experiment metric for control")
    x_control: list[float] = Field(..., description="Pre-experiment covariate for control")
    y_treatment: list[float] = Field(..., description="Post-experiment metric for treatment")
    x_treatment: list[float] = Field(..., description="Pre-experiment covariate for treatment")


class CUPEDResult(BaseModel):
    theta: float
    variance_raw: float
    variance_cuped: float
    variance_reduction_pct: float
    control_cuped_mean: float
    treatment_cuped_mean: float
    summary: str


def apply_cuped(input_data: CUPEDInput) -> CUPEDResult:
    """
    Applies CUPED (Controlled-Experiments Using Pre-Experiment Data) variance reduction.
    Formula: Y_cuped = Y - theta * (X - E[X])
    where theta = Cov(Y, X) / Var(X)
    """
    y = np.array(input_data.y_control + input_data.y_treatment)
    x = np.array(input_data.x_control + input_data.x_treatment)

    cov_matrix = np.cov(y, x)
    cov_yx = cov_matrix[0, 1]
    var_x = cov_matrix[1, 1]

    theta = cov_yx / var_x if var_x > 0 else 0.0
    mean_x = np.mean(x)

    # Adjust control
    y_ctrl = np.array(input_data.y_control)
    x_ctrl = np.array(input_data.x_control)
    y_ctrl_cuped = y_ctrl - theta * (x_ctrl - mean_x)

    # Adjust treatment
    y_trt = np.array(input_data.y_treatment)
    x_trt = np.array(input_data.x_treatment)
    y_trt_cuped = y_trt - theta * (x_trt - mean_x)

    var_raw = float(np.var(y, ddof=1))
    var_cuped = float(np.var(np.concatenate([y_ctrl_cuped, y_trt_cuped]), ddof=1))

    var_red_pct = ((var_raw - var_cuped) / var_raw) * 100.0 if var_raw > 0 else 0.0

    summary = (
        f"CUPED reduced metric variance by {var_red_pct:.2f}% "
        f"(theta={theta:.4f}). Raw var: {var_raw:.5f} -> CUPED var: {var_cuped:.5f}"
    )

    return CUPEDResult(
        theta=float(theta),
        variance_raw=var_raw,
        variance_cuped=var_cuped,
        variance_reduction_pct=float(var_red_pct),
        control_cuped_mean=float(np.mean(y_ctrl_cuped)),
        treatment_cuped_mean=float(np.mean(y_trt_cuped)),
        summary=summary,
    )
