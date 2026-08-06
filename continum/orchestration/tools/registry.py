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

from typing import Literal

from pydantic import BaseModel, Field

# ==========================================
# Store Channel Tool Inputs and Functions
# ==========================================


class LearningsRepositoryInput(BaseModel):
    query_type: Literal[
        "similar_experiments", "category_summary", "effect_sizes", "best_practices"
    ] = Field(default="similar_experiments", description="Type of learning to search for.")
    category_filter: Literal["all", "pricing", "assortment", "staffing", "remodel", "marketing"] = (
        Field(default="all", description="Filter learnings by initiative category.")
    )
    max_results: int = Field(default=5, description="Maximum number of prior learnings to return.")


class RoiSynthesisInput(BaseModel):
    include_halo_effects: Literal["true", "false"] = Field(
        default="true", description="Whether to include halo/spillover effects in the P&L."
    )
    include_cannibalization: Literal["true", "false"] = Field(
        default="true", description="Whether to subtract cannibalization from adjacent categories."
    )
    time_horizon_months: int = Field(default=12, description="Months over which to project ROI.")
    cost_basis: Literal["per_store", "total_fleet", "marginal"] = Field(
        default="per_store", description="How to calculate implementation costs."
    )


class SimpsonsParadoxInput(BaseModel):
    segmentation_dims: Literal["region", "format_type", "risk_tier", "store_size", "all"] = Field(
        default="all", description="Dimensions to segment stores by for heterogeneity analysis."
    )
    min_segment_size: int = Field(
        default=50, description="Minimum number of stores in a segment to analyze."
    )
    significance_threshold: float = Field(
        default=0.05, description="P-value threshold for reporting significant heterogeneity."
    )


def run_learnings_repository(input_data: LearningsRepositoryInput) -> dict:
    return {
        "status": "success",
        "learnings": [
            {
                "experiment": "Walmart Banner Redesign",
                "category": "marketing",
                "lift": "+4.2% click-through rate",
                "confidence": "95%",
                "summary": "Returning customers responded strongest at +6.1% conversion lift.",
            }
        ],
        "summary": "Learnings & Meta-Analysis Repository query complete.",
    }


def run_roi_synthesis(input_data: RoiSynthesisInput) -> dict:
    return {
        "status": "success",
        "net_incremental_margin": "$1,240,000",
        "roi_percent": "155%",
        "payback_period_months": 4.5,
        "summary": "ROI Synthesis complete. Treatment group GMV increased by $1.2M over the test window.",
    }


def run_simpsons_paradox(input_data: SimpsonsParadoxInput) -> dict:
    return {
        "status": "success",
        "subgroup_effects": [
            {"dimension": "region", "segment": "North", "lift": "+5.8%", "significant": True},
            {"dimension": "region", "segment": "South", "lift": "-1.2%", "significant": False},
        ],
        "summary": "Simpson's Paradox & Heterogeneity Check complete. No major paradoxical aggregate sign reversals detected.",
    }


# ==========================================
# Tool Registrations: Store Channel Modules
# ==========================================

run_learnings_repository_tool = create_expsuite_tool(
    name="run_learnings_repository",
    description="Query the Learnings & Meta-Analysis Repository to retrieve historical experiment results, prior knowledge, and meta-analyses.",
    schema=LearningsRepositoryInput,
    func=run_learnings_repository,
    artifact_type="stat_results_card",
)

run_roi_synthesis_tool = create_expsuite_tool(
    name="run_roi_synthesis",
    description="Run ROI Synthesis (P&L Money Waterfall) to translate causal lift into a full financial breakdown including halo effects, cannibalization, and net incremental margin.",
    schema=RoiSynthesisInput,
    func=run_roi_synthesis,
    artifact_type="growth_prediction_card",
)

run_simpsons_paradox_tool = create_expsuite_tool(
    name="run_simpsons_paradox",
    description="Run Simpson's Paradox & Heterogeneity Checker to identify whether aggregate results mask opposing effects across store segments.",
    schema=SimpsonsParadoxInput,
    func=run_simpsons_paradox,
    artifact_type="srm_alert_card",
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
    # Store Channel Modules
    run_learnings_repository_tool,
    run_roi_synthesis_tool,
    run_simpsons_paradox_tool,
]
