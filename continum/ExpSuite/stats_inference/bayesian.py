import numpy as np
from pydantic import BaseModel, Field
from scipy.stats import beta


class BayesianTestInput(BaseModel):
    control_successes: int
    control_failures: int
    treatment_successes: int
    treatment_failures: int
    num_simulations: int = Field(100000, description="Monte Carlo draw count")


class BayesianTestResult(BaseModel):
    prob_beat_control: float
    expected_relative_lift: float
    hdi_lower: float
    hdi_upper: float
    summary: str


def run_bayesian_ab_test(input_data: BayesianTestInput) -> BayesianTestResult:
    """
    Executes Bayesian A/B testing using Beta-Binomial conjugate priors.
    """
    # Uniform Beta(1,1) prior addition
    a_c = input_data.control_successes + 1
    b_c = input_data.control_failures + 1

    a_t = input_data.treatment_successes + 1
    b_t = input_data.treatment_failures + 1

    # Monte Carlo posterior sampling
    ctrl_samples = beta.rvs(a_c, b_c, size=input_data.num_simulations)
    trt_samples = beta.rvs(a_t, b_t, size=input_data.num_simulations)

    prob_beat = float(np.mean(trt_samples > ctrl_samples))
    rel_lifts = (trt_samples - ctrl_samples) / ctrl_samples
    exp_lift = float(np.mean(rel_lifts))

    # 95% Highest Density Interval (HDI)
    hdi_lower = float(np.percentile(rel_lifts, 2.5))
    hdi_upper = float(np.percentile(rel_lifts, 97.5))

    summary = (
        f"Bayesian Analysis: P(Treatment > Control) = {prob_beat * 100:.2f}%. "
        f"Expected relative lift: {exp_lift * 100:.2f}% (95% HDI: [{hdi_lower * 100:.2f}%, {hdi_upper * 100:.2f}%])."
    )

    return BayesianTestResult(
        prob_beat_control=prob_beat,
        expected_relative_lift=exp_lift,
        hdi_lower=hdi_lower,
        hdi_upper=hdi_upper,
        summary=summary,
    )
