# ==========================================
# 3. Imports from ExpSuite.causal
# ==========================================
from continum.ExpSuite.causal import (
    CausalAnalysisInput,
    DiDInput,
    ForecastInput,
    calculate_diff_in_diff,
    run_causal_engine,
    run_monte_carlo_forecast,
)

# ==========================================
# 2. Imports from ExpSuite.planning
# ==========================================
from continum.ExpSuite.planning import (
    MetricPlannerInput,
    OpportunitySizingInput,
    PowerCalcInput,
    TrafficBalanceInput,
    calculate_opportunity_size,
    calculate_power,
    calculate_traffic_balance,
    plan_experiment_metrics,
)

# ==========================================
# 1. Imports from ExpSuite.stats_inference
# ==========================================
from continum.ExpSuite.stats_inference import (
    BayesianTestInput,
    CUPEDInput,
    GuardrailCheckInput,
    SequentialInput,
    SRMInput,
    StatTestInput,
    apply_cuped,
    calculate_hypothesis_test,
    check_guardrail_metric,
    detect_srm,
    run_bayesian_ab_test,
    run_sprt,
)
from continum.orchestration.tools.adapter import create_expsuite_tool

# ==========================================
# Tool Registrations: Stats & Inference
# ==========================================

check_srm_tool = create_expsuite_tool(
    name="check_srm",
    description="Detect Sample Ratio Mismatch (SRM) across experiment variants using Chi-Square goodness-of-fit.",
    schema=SRMInput,
    func=detect_srm,
    artifact_type="srm_alert_card",
)

apply_cuped_tool = create_expsuite_tool(
    name="apply_cuped_variance_reduction",
    description="Reduce metric variance using historical pre-experiment covariates (CUPED).",
    schema=CUPEDInput,
    func=apply_cuped,
    artifact_type="stat_results_card",
)

run_hypothesis_test_tool = create_expsuite_tool(
    name="run_hypothesis_test",
    description="Compute Welch's t-test / Z-test, confidence intervals, and relative lift between Control and Treatment.",
    schema=StatTestInput,
    func=calculate_hypothesis_test,
    artifact_type="stat_results_card",
)

run_sprt_sequential_tool = create_expsuite_tool(
    name="run_sprt_sequential_test",
    description="Run Wald's Sequential Probability Ratio Test (SPRT) to evaluate safe early stopping boundaries.",
    schema=SequentialInput,
    func=run_sprt,
    artifact_type="stat_results_card",
)

run_bayesian_ab_tool = create_expsuite_tool(
    name="run_bayesian_ab_test",
    description="Execute Beta-Binomial Bayesian A/B test to calculate P(Treatment > Control) and 95% HDI intervals.",
    schema=BayesianTestInput,
    func=run_bayesian_ab_test,
    artifact_type="stat_results_card",
)

check_guardrail_tool = create_expsuite_tool(
    name="check_guardrail_degradation",
    description="Evaluate whether secondary guardrail metrics (e.g. latency, cancellations) degraded past safety thresholds.",
    schema=GuardrailCheckInput,
    func=check_guardrail_metric,
    artifact_type="srm_alert_card",
)

# ==========================================
# Tool Registrations: Experiment Planning
# ==========================================

calculate_power_tool = create_expsuite_tool(
    name="calculate_power_and_sample_size",
    description="Calculate required sample size per variant, total sample size, and duration in days for target MDE, power, and alpha.",
    schema=PowerCalcInput,
    func=calculate_power,
    artifact_type="experiment_brief",
)

calculate_opportunity_tool = create_expsuite_tool(
    name="calculate_opportunity_size",
    description="Estimate annual and quarterly incremental conversions and revenue impact for a target lift hypothesis.",
    schema=OpportunitySizingInput,
    func=calculate_opportunity_size,
    artifact_type="growth_prediction_card",
)

plan_metrics_tool = create_expsuite_tool(
    name="plan_experiment_metrics",
    description="Map primary retail metrics to recommended secondary and guardrail metrics based on domain area.",
    schema=MetricPlannerInput,
    func=plan_experiment_metrics,
    artifact_type="experiment_brief",
)

balance_traffic_tool = create_expsuite_tool(
    name="balance_traffic_allocation",
    description="Compute variant traffic allocation percentages and verify multi-arm split integrity.",
    schema=TrafficBalanceInput,
    func=calculate_traffic_balance,
    artifact_type="experiment_brief",
)

# ==========================================
# Tool Registrations: Causal & Forecasting
# ==========================================

calculate_did_tool = create_expsuite_tool(
    name="calculate_diff_in_diff",
    description="Compute Difference-in-Differences (DiD) treatment effects for observational or non-randomized rollouts.",
    schema=DiDInput,
    func=calculate_diff_in_diff,
    artifact_type="stat_results_card",
)

run_forecast_tool = create_expsuite_tool(
    name="run_monte_carlo_growth_forecast",
    description="Run Monte Carlo simulation to forecast quarterly and annual revenue growth with P10/P50/P90 confidence bounds.",
    schema=ForecastInput,
    func=run_monte_carlo_forecast,
    artifact_type="growth_prediction_card",
)

run_causal_engine_tool = create_expsuite_tool(
    name="run_causal_engine",
    description="Coordinator tool for observational analysis (DiD) or Monte Carlo growth forecasting.",
    schema=CausalAnalysisInput,
    func=run_causal_engine,
    artifact_type="growth_prediction_card",
)

# ==========================================
# Consolidated Master Tool List Export
# ==========================================

all_experimentation_tools = [
    # Stats & Inference
    check_srm_tool,
    apply_cuped_tool,
    run_hypothesis_test_tool,
    run_sprt_sequential_tool,
    run_bayesian_ab_tool,
    check_guardrail_tool,
    # Planning & Sizing
    calculate_power_tool,
    calculate_opportunity_tool,
    plan_metrics_tool,
    balance_traffic_tool,
    # Causal & Forecasting
    calculate_did_tool,
    run_forecast_tool,
    run_causal_engine_tool,
]
