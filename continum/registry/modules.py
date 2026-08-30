"""Canonical Analytics Lab module contract.

The registry is intentionally framework-independent so it can be consumed by
HTTP routes, agents, execution services, and deployment validation. The
frontend remains on its legacy registry during the migration and must obtain
module documentation through the API rather than duplicate it.
"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ModuleDefinition:
    id: str
    title: str
    phase: str
    description: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    dependencies: tuple[str, ...]
    documentation: str
    execution_handler: str
    supported_questions: tuple[str, ...]
    permissions: tuple[str, ...] = ("CAN_QUERY",)
    ui_component: str = "AnalyticsLabModulePanel"

    @property
    def category(self) -> str:
        return self.phase

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category
        return data


def _module(
    id: str,
    title: str,
    phase: str,
    description: str,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
    dependencies: tuple[str, ...],
    documentation: str,
    execution_handler: str,
    supported_questions: tuple[str, ...],
) -> ModuleDefinition:
    return ModuleDefinition(
        id,
        title,
        phase,
        description,
        inputs,
        outputs,
        dependencies,
        documentation,
        execution_handler,
        supported_questions,
    )


MODULE_REGISTRY: tuple[ModuleDefinition, ...] = (
    _module(
        "data-validation",
        "Data Validation",
        "foundation",
        "Checks completeness, null rates, and integrity constraints across experiment tables.",
        ("source tables", "validation rules"),
        ("quality report", "failed checks"),
        (),
        "Validate data before designing or interpreting an experiment.",
        "not_implemented",
        ("Is my data ready?", "What data quality issues exist?"),
    ),
    _module(
        "dimension-setup",
        "Dimension Setup",
        "foundation",
        "Configures store segmentation and stratification for balanced experiment groups.",
        ("store attributes", "segmentation strategy"),
        ("dimension map", "strata"),
        ("data-validation",),
        "Define dimensions used for matching, reporting, and heterogeneous-effect analysis.",
        "not_implemented",
        ("How should stores be segmented?", "Which dimensions should I use?"),
    ),
    _module(
        "distribution-shift",
        "Distribution Shift",
        "foundation",
        "Detects pre/post changes in covariate distributions that could bias causal estimates.",
        ("pre-period data", "post-period data", "covariates"),
        ("shift diagnostics", "risk flags"),
        ("data-validation",),
        "Check population stability before trusting a causal comparison.",
        "not_implemented",
        ("Did the population change?", "Are covariates drifting?"),
    ),
    _module(
        "pipeline-health",
        "Pipeline Health",
        "foundation",
        "Monitors data freshness, lag, and feed reliability for experiment metrics.",
        ("data sources", "freshness thresholds"),
        ("pipeline health report", "alerts"),
        ("data-validation",),
        "Use to verify that measurement data is timely and reliable.",
        "not_implemented",
        ("Is the data pipeline healthy?", "Is data delayed?"),
    ),
    _module(
        "schema-discovery",
        "Schema Discovery",
        "foundation",
        "Maps available data tables, dimensions, measures, and join relationships.",
        ("catalog and schema scope",),
        ("schema map", "join recommendations"),
        (),
        "Start here when the available data assets are unknown.",
        "run_ingestion_workflow",
        ("What tables are available?", "How do these tables join?"),
    ),
    _module(
        "watchtower",
        "Watchtower",
        "foundation",
        "Continuously monitors anomalies, metric spikes, and data-quality alerts.",
        ("monitored metrics", "alert thresholds"),
        ("anomaly alerts", "incident summary"),
        ("pipeline-health",),
        "Use during operations to detect unexpected data or metric behavior.",
        "not_implemented",
        ("Are there anomalies?", "What alerts need attention?"),
    ),
    _module(
        "opportunity-sizing",
        "Opportunity Sizing",
        "preplanning",
        "Estimates addressable impact and expected lift at fleet-expansion tiers.",
        ("baseline volume", "target lift", "unit economics"),
        ("impact estimate", "confidence range"),
        ("metrics-tracking",),
        "Quantify expected business value before investing in an experiment.",
        "calculate_opportunity_size",
        ("How large is the opportunity?", "What is the expected impact?"),
    ),
    _module(
        "metrics-tracking",
        "Metrics Tracking",
        "preplanning",
        "Defines primary, secondary, and guardrail metrics for an experiment.",
        ("hypothesis", "business objective"),
        ("metric plan", "measurement definitions"),
        ("schema-discovery",),
        "Specify success measures and guardrails before the experiment starts.",
        "plan_experiment_metrics",
        ("What metrics should we track?", "What is a good guardrail metric?"),
    ),
    _module(
        "experiment-type",
        "Experiment Type",
        "preplanning",
        "Chooses an appropriate design: randomized, switchback, geo, or stepped-wedge.",
        ("hypothesis", "operational constraints", "unit of treatment"),
        ("recommended design", "rationale"),
        ("metrics-tracking",),
        "Select a design that supports the intended causal claim.",
        "not_implemented",
        ("Which experiment design should I use?", "Should this be A/B or DiD?"),
    ),
    _module(
        "power-calculator",
        "Power Calculator",
        "preplanning",
        "Computes required sample size and test duration from MDE, variance, and significance.",
        ("baseline rate", "minimum detectable effect", "alpha", "power"),
        ("sample size", "duration estimate"),
        ("metrics-tracking",),
        "Use to determine whether a design can detect a meaningful effect.",
        "calculate_power_and_sample_size",
        ("How many stores do I need?", "What MDE can we detect?"),
    ),
    _module(
        "balance-diagnostics",
        "Balance Diagnostics",
        "preplanning",
        "Checks covariate balance between treatment and control before and after matching.",
        ("treatment panel", "control panel", "covariates"),
        ("balance report", "standardized differences"),
        ("dimension-setup",),
        "Verify comparable groups before a causal analysis.",
        "balance_traffic_allocation",
        ("Are treatment and control balanced?", "How good is the matching?"),
    ),
    _module(
        "brief-generator",
        "Brief Generator",
        "preplanning",
        "Compiles the experiment setup into a shareable specification document.",
        ("hypothesis", "metric plan", "design", "power plan"),
        ("experiment brief",),
        ("metrics-tracking", "experiment-type", "power-calculator"),
        "Generate an auditable experiment brief once the design is ready.",
        "not_implemented",
        ("Create an experiment brief.", "Summarize the planned test."),
    ),
    _module(
        "audience-selection",
        "Audience Selection",
        "preplanning",
        "Configures stores in treatment and control panels.",
        ("eligible population", "allocation constraints"),
        ("audience assignment", "exclusions"),
        ("balance-diagnostics",),
        "Select eligible units while preserving balance and operational feasibility.",
        "balance_traffic_allocation",
        ("Which stores should be in the test?", "How should I allocate treatment?"),
    ),
    _module(
        "experiment-analysis",
        "Experiment Analysis",
        "monitoring",
        "Provides interim results, confidence intervals, and decision readiness for an in-flight test.",
        ("experiment outcomes", "analysis window"),
        ("interim results", "decision readiness"),
        ("metrics-tracking",),
        "Review an active experiment without overstating interim evidence.",
        "run_experiment_analysis_workflow",
        ("How is the experiment performing?", "Are results significant yet?"),
    ),
    _module(
        "health-monitor",
        "Health Monitor",
        "monitoring",
        "Checks sample ratio mismatch, allocation drift, and experiment-integrity issues.",
        ("assignment data", "event data"),
        ("health report", "integrity alerts"),
        ("audience-selection",),
        "Use throughout execution to detect conditions that invalidate inference.",
        "run_health_monitoring_workflow",
        ("Is the experiment healthy?", "Is there an SRM?"),
    ),
    _module(
        "sequential-testing",
        "Sequential Testing",
        "monitoring",
        "Calculates always-valid confidence intervals and early-stopping boundaries.",
        ("cumulative outcomes", "stopping policy"),
        ("sequential evidence", "stopping recommendation"),
        ("experiment-analysis",),
        "Use only with a pre-specified sequential decision policy.",
        "run_sprt_sequential_test",
        ("Can we stop early?", "How do we avoid peeking bias?"),
    ),
    _module(
        "causal-did",
        "Causal Inference (DiD)",
        "causal",
        "Uses DiD-family estimators to isolate incremental treatment lift.",
        ("treatment timing", "outcomes", "comparison group", "covariates"),
        ("treatment effect", "uncertainty", "diagnostics"),
        ("balance-diagnostics",),
        "Difference-in-differences estimates a relative change between treated and comparison units; its assumptions must be checked.",
        "calculate_diff_in_diff",
        ("Explain DID.", "What is the treatment effect?", "Run causal analysis."),
    ),
    _module(
        "forecasting",
        "Forecasting",
        "causal",
        "Generates counterfactual projections and full-fleet scale simulations.",
        ("time series", "forecast horizon", "model settings"),
        ("forecast", "prediction interval", "counterfactual"),
        ("experiment-analysis",),
        "Forecast expected outcomes and compare them with observed performance.",
        "run_monte_carlo_growth_forecast",
        ("What will happen next?", "What is the counterfactual?"),
    ),
    _module(
        "learnings-repository",
        "Learnings Repository",
        "causal",
        "Retrieves historical experiment results, meta-analyses, and institutional knowledge.",
        ("research question", "filters"),
        ("relevant learnings", "evidence summary"),
        (),
        "Search governed historical learnings before designing or scaling a test.",
        "not_implemented",
        ("What have we learned before?", "Find similar experiments."),
    ),
    _module(
        "roi-synthesis",
        "ROI Synthesis",
        "causal",
        "Translates causal lift into a P&L including halo effects and cannibalization.",
        ("causal effect", "costs", "margin assumptions"),
        ("ROI waterfall", "payback estimate"),
        ("causal-did",),
        "Convert an incremental effect into a transparent financial decision model.",
        "not_implemented",
        ("What is the ROI?", "What is the payback period?"),
    ),
    _module(
        "simpsons-paradox",
        "Simpson's Paradox Checker",
        "causal",
        "Tests whether aggregate effects mask opposing segment-level effects.",
        ("outcomes", "segmentation dimensions"),
        ("heterogeneity report", "paradox warnings"),
        ("causal-did", "dimension-setup"),
        "Investigate segment effects before acting on aggregate treatment results.",
        "not_implemented",
        ("Is there Simpson's paradox?", "Which segments respond differently?"),
    ),
)

MODULE_BY_ID = {module.id: module for module in MODULE_REGISTRY}


def list_modules(phase: str | None = None) -> list[ModuleDefinition]:
    """Return modules, optionally limited to a canonical phase id."""
    if phase in (None, "", "all"):
        return list(MODULE_REGISTRY)
    return [module for module in MODULE_REGISTRY if module.phase == phase]


def get_module(module_id: str) -> ModuleDefinition | None:
    return MODULE_BY_ID.get(module_id)
