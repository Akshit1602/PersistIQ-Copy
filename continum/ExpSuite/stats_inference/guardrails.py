from pydantic import BaseModel, Field


class GuardrailCheckInput(BaseModel):
    metric_name: str
    control_value: float
    treatment_value: float
    max_allowed_degradation_pct: float = Field(
        0.02, description="Max acceptable negative delta e.g. 2%"
    )


class GuardrailReport(BaseModel):
    metric_name: str
    control_value: float
    treatment_value: float
    degradation_pct: float
    is_violated: bool
    summary: str


def check_guardrail_metric(input_data: GuardrailCheckInput) -> GuardrailReport:
    """
    Evaluates whether a guardrail metric experienced unacceptable degradation.
    """
    c_val = input_data.control_value
    t_val = input_data.treatment_value

    if c_val != 0:
        delta_pct = (t_val - c_val) / c_val
    else:
        delta_pct = 0.0

    # Degradation means the metric degraded past threshold (e.g. latency increased or conversion dropped)
    is_violated = delta_pct < -abs(input_data.max_allowed_degradation_pct)

    summary = (
        f"Guardrail '{input_data.metric_name}': Delta = {delta_pct * 100:.2f}%. "
        f"Status: {'VIOLATED! Guardrail degraded beyond allowed threshold.' if is_violated else 'PASSED'}"
    )

    return GuardrailReport(
        metric_name=input_data.metric_name,
        control_value=c_val,
        treatment_value=t_val,
        degradation_pct=float(delta_pct),
        is_violated=is_violated,
        summary=summary,
    )
