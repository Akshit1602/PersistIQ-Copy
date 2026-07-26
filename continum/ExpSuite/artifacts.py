from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SignificanceVerdict(str, Enum):
    SIGNIFICANT = "significant"
    NOT_SIGNIFICANT = "not_significant"
    INCONCLUSIVE = "inconclusive"
    SRM_DETECTED = "srm_detected"
    UNDERPOWERED = "underpowered"


class ShipRecommendation(str, Enum):
    SHIP = "ship"
    DO_NOT_SHIP = "do_not_ship"
    EXTEND = "extend"
    INVESTIGATE = "investigate"
    PARTIAL = "partial_rollout"


class AnomalySeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class PowerAnalysis(BaseModel):
    artifact_version: str = "1.0"
    artifact_id: UUID = Field(default_factory=uuid4)
    experiment_id: str
    primary_metric: str
    baseline_rate: float
    mde_abs: float
    mde_rel: float
    alpha: float = 0.05
    power: float = 0.80
    n_variants: int = 2
    n_per_variant: int
    n_total: int
    daily_eligible_traffic: float
    days_required: int
    planned_end_date: str
    effect_size_h: float
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    analyst: str = ""

    def to_llm_context(self) -> str:
        return (
            f"POWER ANALYSIS\n"
            f"Metric: {self.primary_metric}\n"
            f"Baseline: {self.baseline_rate:.2%}  MDE: {self.mde_rel:.1%} rel ({self.mde_abs*100:.3f}pp abs)\n"
            f"α={self.alpha}  Power={self.power:.0%}\n"
            f"Required n: {self.n_total:,} total ({self.n_per_variant:,}/variant)\n"
            f"Duration: {self.days_required} days  End: {self.planned_end_date}\n"
        )


class OpportunitySizing(BaseModel):
    artifact_version: str = "1.0"
    artifact_id: UUID = Field(default_factory=uuid4)
    experiment_id: str = ""
    monthly_inquiries: float
    current_ior: float
    target_ior: float
    avg_order_value: float
    gross_margin: float
    time_horizon_months: float = 12
    ior_gap_pp: float
    current_orders_monthly: float
    target_orders_monthly: float
    incremental_orders_monthly: float
    incremental_revenue_monthly: float
    incremental_gm_monthly: float
    incremental_orders_12mo: float = 0.0
    incremental_revenue_12mo: float = 0.0
    incremental_gm_12mo: float = 0.0
    computed_at: datetime = Field(default_factory=datetime.utcnow)

    def to_llm_context(self) -> str:
        return (
            f"OPPORTUNITY SIZING\n"
            f"Monthly inquiries: {self.monthly_inquiries:,.0f}\n"
            f"IOR gap: {self.current_ior:.2%} → {self.target_ior:.2%} ({self.ior_gap_pp:+.2f}pp)\n"
            f"Incremental orders/mo: {self.incremental_orders_monthly:,.1f}\n"
            f"Incremental revenue/mo: ${self.incremental_revenue_monthly:,.0f}\n"
            f"12-month revenue upside: ${self.incremental_revenue_12mo:,.0f}\n"
        )


class MetricDelta(BaseModel):
    artifact_version: str = "1.0"
    metric_name: str
    metric_display_name: str
    control_variant: str
    treatment_variant: str
    n_control: int
    n_treatment: int
    rate_control: Optional[float] = None
    rate_treatment: Optional[float] = None
    delta_pp: Optional[float] = None
    mean_control: Optional[float] = None
    mean_treatment: Optional[float] = None
    delta_abs: float
    delta_rel: float
    ci_lo: float
    ci_hi: float
    p_value: float
    effect_size: float
    is_significant: bool
    direction: str
    alpha: float = 0.05
    method: str = "z_test"
    bonferroni_applied: bool = False
    n_comparisons: int = 1


class SliceFinding(BaseModel):
    artifact_version: str = "1.0"
    experiment_id: str
    metric_name: str
    dimension_name: str
    dimension_value: str
    n_slice: int
    delta: MetricDelta
    is_heterogeneous: bool
    simpsons_paradox_flag: bool = False
    interaction_p_value: Optional[float] = None


class GuardrailViolation(BaseModel):
    artifact_version: str = "1.0"
    artifact_id: UUID = Field(default_factory=uuid4)
    experiment_id: str
    guardrail_name: str
    metric_name: str
    severity: str
    condition: str
    threshold: float
    observed_value: float
    baseline_value: Optional[float] = None
    violation_magnitude: float
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    recommendation: str = "Do not ship without investigation"

    def to_llm_context(self) -> str:
        return (
            f"GUARDRAIL VIOLATION [{self.severity.upper()}]\n"
            f"Guardrail: {self.guardrail_name}  Metric: {self.metric_name}\n"
            f"Condition: {self.condition}  Threshold: {self.threshold}\n"
            f"Observed: {self.observed_value}  Magnitude: {self.violation_magnitude:+.4f}\n"
            f"Action: {self.recommendation}\n"
        )


class ExperimentResult(BaseModel):
    artifact_version: str = "1.0"
    artifact_id: UUID = Field(default_factory=uuid4)
    experiment_id: str
    experiment_name: str
    primary_metric: str
    analysis_method: str
    analyst: str
    analysed_at: datetime = Field(default_factory=datetime.utcnow)
    primary_delta: MetricDelta
    secondary_deltas: List[MetricDelta] = Field(default_factory=list)
    slice_findings: List[SliceFinding] = Field(default_factory=list)
    guardrail_violations: List[GuardrailViolation] = Field(default_factory=list)
    srm_detected: bool = False
    srm_p_value: Optional[float] = None
    srm_chi2: Optional[float] = None
    power_analysis: Optional[PowerAnalysis] = None
    actual_n: Optional[int] = None
    verdict: SignificanceVerdict
    ship_recommendation: ShipRecommendation
    ship_blockers: List[str] = Field(default_factory=list)
    ship_enablers: List[str] = Field(default_factory=list)
    learnings: List[Dict[str, Any]] = Field(default_factory=list)

    @property
    def is_shippable(self) -> bool:
        return self.ship_recommendation in (
            ShipRecommendation.SHIP,
            ShipRecommendation.PARTIAL,
        ) and not any(v.severity == "blocker" for v in self.guardrail_violations)

    @property
    def n_total(self) -> int:
        return self.primary_delta.n_control + self.primary_delta.n_treatment

    def to_llm_context(self) -> str:
        violations_text = ""
        if self.guardrail_violations:
            violations_text = "\nGUARDRAIL VIOLATIONS:\n" + "\n".join(
                v.to_llm_context() for v in self.guardrail_violations
            )
        slice_text = ""
        sig_slices = [s for s in self.slice_findings if s.delta.is_significant]
        if sig_slices:
            slice_text = "\nSIGNIFICANT SLICES:\n" + "\n".join(
                f"  {s.dimension_name}={s.dimension_value}: "
                f"Δ={s.delta.delta_pp:+.2f}pp p={s.delta.p_value:.4f}"
                for s in sig_slices[:8]
            )
        secondary_text = ""
        if self.secondary_deltas:
            secondary_text = "\nSECONDARY METRICS:\n" + "\n".join(
                f"  {d.metric_display_name}: Δ={d.delta_abs:+.4f} p={d.p_value:.4f} "
                f"{'✓' if d.is_significant else '—'}"
                for d in self.secondary_deltas
            )
        return (
            f"EXPERIMENT RESULT v{self.artifact_version}\n{'='*60}\n"
            f"Experiment: {self.experiment_name} ({self.experiment_id})\n"
            f"Method: {self.analysis_method}  Analyst: {self.analyst}\n"
            f"\nPRIMARY METRIC: {self.primary_delta.metric_display_name}\n"
            f"n_ctrl={self.primary_delta.n_control:,}  n_treat={self.primary_delta.n_treatment:,}\n"
            f"Δ={self.primary_delta.delta_pp:+.2f}pp "
            f"[{self.primary_delta.ci_lo:+.2f},{self.primary_delta.ci_hi:+.2f}] "
            f"p={self.primary_delta.p_value:.4f}\n"
            f"Significant: {self.primary_delta.is_significant}  Direction: {self.primary_delta.direction}\n"
            f"\nVERDICT: {self.verdict.value.upper()}\n"
            f"Ship: {self.ship_recommendation.value.upper()}\n"
            f"SRM: {self.srm_detected}"
            + (f" (p={self.srm_p_value:.4f})" if self.srm_p_value else "")
            + f"\nViolations: {len(self.guardrail_violations)}\n"
            f"Blockers: {'; '.join(self.ship_blockers) or 'None'}\n"
            + violations_text
            + secondary_text
            + slice_text
        )


class CausalEstimate(BaseModel):
    artifact_version: str = "1.0"
    artifact_id: UUID = Field(default_factory=uuid4)
    experiment_id: str
    method: str
    estimand: str = "ATT"
    outcome_metric: str
    estimate: float
    std_error: float
    ci_lo: float
    ci_hi: float
    p_value: float
    is_significant: bool
    method_specific: Dict[str, Any] = Field(default_factory=dict)
    validity_checks: Dict[str, Any] = Field(default_factory=dict)
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    analyst: str = ""
    notes: str = ""

    def to_llm_context(self) -> str:
        validity = "; ".join(
            f"{k}={'PASS' if v else 'FAIL'}"
            for k, v in self.validity_checks.items()
            if isinstance(v, bool)
        )
        return (
            f"CAUSAL ESTIMATE [{self.method.upper()}]\n"
            f"Experiment: {self.experiment_id}  Metric: {self.outcome_metric}\n"
            f"Estimand: {self.estimand}\n"
            f"Estimate: {self.estimate:+.4f}  SE: {self.std_error:.4f}\n"
            f"CI: [{self.ci_lo:+.4f},{self.ci_hi:+.4f}]  p={self.p_value:.4f}\n"
            f"Significant: {self.is_significant}\n"
            + (f"Validity: {validity}\n" if validity else "")
        )


class CounterfactualForecast(BaseModel):
    artifact_version: str = "1.0"
    artifact_id: UUID = Field(default_factory=uuid4)
    experiment_id: str
    method: str
    outcome_metric: str
    intervention_date: str
    post_period_estimate: float
    post_period_ci_lo: float
    post_period_ci_hi: float
    cumulative_effect: float
    cumulative_ci_lo: float
    cumulative_ci_hi: float
    p_value: Optional[float] = None
    is_significant: bool
    model_fit_metrics: Dict[str, float] = Field(default_factory=dict)
    computed_at: datetime = Field(default_factory=datetime.utcnow)

    def to_llm_context(self) -> str:
        return (
            f"COUNTERFACTUAL FORECAST [{self.method.upper()}]\n"
            f"Experiment: {self.experiment_id}  Metric: {self.outcome_metric}\n"
            f"Intervention: {self.intervention_date}\n"
            f"Post-period: {self.post_period_estimate:+.4f} "
            f"[{self.post_period_ci_lo:+.4f},{self.post_period_ci_hi:+.4f}]\n"
            f"Cumulative: {self.cumulative_effect:+.4f} "
            f"[{self.cumulative_ci_lo:+.4f},{self.cumulative_ci_hi:+.4f}]\n"
            f"Significant: {self.is_significant}\n"
        )


class AnomalyReport(BaseModel):
    artifact_version: str = "1.0"
    artifact_id: UUID = Field(default_factory=uuid4)
    anomaly_type: str
    severity: AnomalySeverity
    metric_affected: str
    dimension_name: Optional[str] = None
    dimension_value: Optional[str] = None
    detected_at: datetime
    baseline_value: float
    observed_value: float
    deviation_z_score: float
    pct_change: float
    experiment_ids_concurrent: List[str] = Field(default_factory=list)
    pipeline_hint: str = ""
    recommended_action: str
    resolved: bool = False

    def to_llm_context(self) -> str:
        return (
            f"ANOMALY [{self.severity.value.upper()}]: {self.anomaly_type}\n"
            f"Metric: {self.metric_affected}"
            + (
                f"  Slice: {self.dimension_name}={self.dimension_value}"
                if self.dimension_name
                else ""
            )
            + f"\nBaseline: {self.baseline_value:.4f} → Observed: {self.observed_value:.4f}\n"
            f"Δ={self.pct_change:+.1f}%  z={self.deviation_z_score:+.2f}\n"
            f"Action: {self.recommended_action}\n"
        )


class SequentialTestState(BaseModel):
    artifact_version: str = "1.0"
    artifact_id: UUID = Field(default_factory=uuid4)
    experiment_id: str
    metric_name: str
    variant: str
    n_control: int
    n_treatment: int
    current_statistic: float
    threshold: float
    current_ior_ctrl: float
    current_ior_treat: float
    current_delta_pp: float
    stop_recommended: bool
    stop_reason: str = ""
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    def to_llm_context(self) -> str:
        status = "STOP" if self.stop_recommended else "CONTINUE"
        return (
            f"SEQUENTIAL TEST [{status}]\n"
            f"Experiment: {self.experiment_id}  n={self.n_control+self.n_treatment:,}\n"
            f"IOR: {self.current_ior_ctrl:.3%} → {self.current_ior_treat:.3%} "
            f"(Δ={self.current_delta_pp:+.3f}pp)\n"
            f"Statistic: {self.current_statistic:.3f}  Threshold: {self.threshold:.1f}\n"
        )
