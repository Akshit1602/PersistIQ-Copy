from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator


# ─────────────────────────────────────────────────────────────────────────────
# ENUMERATIONS
# ─────────────────────────────────────────────────────────────────────────────

class EntityType(str, Enum):
    BUYER       = "buyer"
    ACCOUNT     = "account"
    INQUIRY     = "inquiry"
    ORDER       = "order"
    EXPERIMENT  = "experiment"
    DOCUMENT    = "document"


class EventType(str, Enum):
    INQUIRY_CREATED    = "inquiry_created"
    ORDER_PLACED       = "order_placed"
    EXP_ASSIGNED       = "experiment_assigned"
    FEATURE_ACTIVATED  = "feature_activated"
    SESSION_STARTED    = "session_started"
    FORM_ABANDONED     = "form_abandoned"
    PAYMENT_INITIATED  = "payment_initiated"
    PAYMENT_COMPLETED  = "payment_completed"
    DOCUMENT_UPLOADED  = "document_uploaded"


class MetricType(str, Enum):
    RATE  = "rate"
    MEAN  = "mean"
    COUNT = "count"
    SUM   = "sum"
    RATIO = "ratio"


class MetricDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER  = "lower_is_better"
    NEUTRAL          = "neutral"


class DimensionType(str, Enum):
    CATEGORICAL = "categorical"
    CONTINUOUS  = "continuous"
    DATETIME    = "datetime"


class ExperimentStatus(str, Enum):
    DRAFT        = "draft"
    POWER_CHECK  = "power_check"
    LIVE         = "live"
    STOPPED      = "stopped"
    COMPLETED    = "completed"
    ARCHIVED     = "archived"


class HypothesisConfidence(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class LearningConfidence(str, Enum):
    CONFIRMED  = "confirmed"
    PROBABLE   = "probable"
    TENTATIVE  = "tentative"


class EvidenceType(str, Enum):
    CAUSAL        = "causal"
    CORRELATIONAL = "correlational"
    QUALITATIVE   = "qualitative"


class GuardrailSeverity(str, Enum):
    BLOCKER = "blocker"
    WARNING = "warning"


class GuardrailCondition(str, Enum):
    MIN            = "min"
    MAX            = "max"
    NO_DEGRADATION = "no_degradation"


# ─────────────────────────────────────────────────────────────────────────────
# PRIMITIVE CONCEPTS
# ─────────────────────────────────────────────────────────────────────────────

class Entity(BaseModel):
    id:           UUID            = Field(default_factory=uuid4)
    entity_type:  EntityType
    canonical_id: str             = Field(..., description="The resolved, deduplicated identity key")
    source_ids:   List[str]       = Field(default_factory=list, description="Raw IDs from all contributing sources")
    created_at:   datetime
    properties:   Dict[str, Any]  = Field(default_factory=dict)

    class Config:
        frozen = True


class Event(BaseModel):
    id:                  UUID           = Field(default_factory=uuid4)
    event_type:          str
    entity_id:           str
    related_entity_ids:  List[str]      = Field(default_factory=list)
    occurred_at:         datetime
    ingested_at:         datetime
    properties:          Dict[str, Any] = Field(default_factory=dict)
    source_system:       str            = Field(..., description="snowflake | statsig | csv | synthetic")

    class Config:
        frozen = True


class Dimension(BaseModel):
    name:           str                       = Field(..., description="snake_case, globally unique")
    display_name:   str
    dimension_type: DimensionType
    allowed_values: Optional[List[str]]       = None   # None = open-ended
    value_aliases:  Dict[str, str]            = Field(default_factory=dict)   # "ENT" → "Enterprise"
    owner:          str
    version:        int                       = 1
    deprecated:     bool                      = False

    @validator("name")
    def name_must_be_snake_case(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"Dimension name must be snake_case, got: {v!r}")
        return v

    def resolve_value(self, raw: str) -> str:
        return self.value_aliases.get(raw, raw)

    def validate_value(self, value: str) -> bool:
        if self.allowed_values is None:
            return True
        return self.resolve_value(value) in self.allowed_values


class Metric(BaseModel):
    name:                  str                     = Field(..., description="globally unique, snake_case")
    display_name:          str
    description:           str
    metric_type:           MetricType
    numerator_event:       str                     = Field(..., description="event_type that increments numerator")
    denominator_event:     Optional[str]           = None        # None for counts/sums
    direction:             MetricDirection
    unit:                  str                     = Field(..., description="% | $ | count | days | seconds")
    guardrail_min:         Optional[float]         = None
    guardrail_max:         Optional[float]         = None
    owner:                 str
    dependent_dimensions:  List[str]               = Field(default_factory=list)
    version:               int                     = 1
    deprecated:            bool                    = False
    superseded_by:         Optional[str]           = None        # metric name if deprecated

    @validator("name")
    def name_must_be_snake_case(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"Metric name must be snake_case, got: {v!r}")
        return v

    class Config:
        frozen = True


class Segment(BaseModel):
    name:                  str
    description:           str
    entity_type:           EntityType
    inclusion_predicate:   str                     = Field(..., description="SQL-safe filter expression")
    estimated_size:        Optional[int]           = None
    dimensions_used:       List[str]               = Field(default_factory=list)
    owner:                 str
    version:               int                     = 1

    @validator("inclusion_predicate")
    def no_dangerous_sql(cls, v: str) -> str:
        forbidden = ["drop", "delete", "truncate", "insert", "update", "--", ";"]
        vl = v.lower()
        for kw in forbidden:
            if kw in vl:
                raise ValueError(f"Unsafe SQL keyword in inclusion_predicate: {kw!r}")
        return v


class Hypothesis(BaseModel):
    id:                        UUID                   = Field(default_factory=uuid4)
    statement:                 str                    = Field(..., description="e.g. 'Reducing quote complexity will increase IOR by 2pp'")
    primary_metric:            str
    secondary_metrics:         List[str]              = Field(default_factory=list)
    predicted_direction:       str                    = Field(..., description="positive | negative")
    predicted_magnitude_abs:   Optional[float]        = None
    predicted_magnitude_rel:   Optional[float]        = None
    confidence:                HypothesisConfidence
    rationale:                 str
    owner:                     str
    created_at:                datetime               = Field(default_factory=datetime.utcnow)
    domain:                    str                    = ""          # e.g. "pricing" | "UX" | "onboarding"
    tags:                      List[str]              = Field(default_factory=list)


class Exposure(BaseModel):
    exposure_id:       UUID                          = Field(default_factory=uuid4)
    experiment_id:     str
    entity_id:         str
    variant_name:      str
    exposed_at:        datetime
    assignment_hash:   Optional[str]                 = None   # for reproducibility auditing
    source_system:     str                           = Field(..., description="statsig | internal | manual")

    class Config:
        frozen = True


class Guardrail(BaseModel):
    name:                  str
    metric:                str                           # metric name in registry
    condition:             GuardrailCondition
    threshold:             float
    relative_threshold:    Optional[float]               = None    # allow up to X% relative degradation
    severity:              GuardrailSeverity
    applies_to_segments:   List[str]                     = Field(default_factory=list)    # empty = global
    owner:                 str
    description:           str                           = ""

    def is_violated(self, observed_value: float, baseline_value: Optional[float] = None) -> bool:
        if self.condition == GuardrailCondition.MIN:
            return observed_value < self.threshold
        elif self.condition == GuardrailCondition.MAX:
            return observed_value > self.threshold
        elif self.condition == GuardrailCondition.NO_DEGRADATION:
            if baseline_value is None:
                return False
            if self.relative_threshold is not None:
                degradation_pct = (baseline_value - observed_value) / abs(baseline_value) if baseline_value != 0 else 0
                return degradation_pct > self.relative_threshold
            return observed_value < self.threshold
        return False


class Experiment(BaseModel):
    id:                    str                           = Field(..., description="human-readable e.g. 'PRICING_Q12026_AB'")
    name:                  str
    hypothesis_id:         UUID
    primary_metric:        str
    secondary_metrics:     List[str]                     = Field(default_factory=list)
    guardrails:            List[str]                     = Field(default_factory=list)    # guardrail names
    segments:              List[str]                     = Field(default_factory=list)    # segment names
    variants:              List[str]                     = Field(default_factory=list)
    control_variant:       str                           = "control"
    owner:                 str
    team:                  str
    status:                ExperimentStatus             = ExperimentStatus.DRAFT
    launch_date:           Optional[datetime]           = None
    stop_date:             Optional[datetime]           = None
    planned_duration_days: Optional[int]                = None
    platform:              str                          = "web"
    feature_area:          str                          = ""
    description:           str                          = ""
    tags:                  List[str]                    = Field(default_factory=list)

    @property
    def is_live(self) -> bool:
        return self.status == ExperimentStatus.LIVE

    @property
    def duration_days(self) -> Optional[int]:
        if self.launch_date and self.stop_date:
            return (self.stop_date - self.launch_date).days
        return None


class Analysis(BaseModel):
    id:              UUID           = Field(default_factory=uuid4)
    experiment_id:   str
    method:          str            = Field(..., description="ab_test | did | psm | rdd | synthetic_control | ...")
    analyst:         str
    run_at:          datetime       = Field(default_factory=datetime.utcnow)
    parameters:      Dict[str, Any] = Field(default_factory=dict)
    artifact_ids:    List[UUID]     = Field(default_factory=list)
    notes:           str            = ""


class Learning(BaseModel):
    id:                     UUID                          = Field(default_factory=uuid4)
    experiment_ids:         List[str]
    statement:              str                           = Field(..., description="The generalisable insight")
    domain:                 str                           = Field(..., description="pricing | UX | onboarding | retention ...")
    applicable_segments:    List[str]                     = Field(default_factory=list)
    applicable_metrics:     List[str]                     = Field(default_factory=list)
    confidence:             LearningConfidence
    evidence_type:          EvidenceType
    effect_magnitude:       Optional[str]                 = None    # e.g. "+2-3pp IOR"
    replicated_in:          List[str]                     = Field(default_factory=list)    # other experiment IDs
    contradicted_by:        List[str]                     = Field(default_factory=list)    # experiment IDs
    created_at:             datetime                      = Field(default_factory=datetime.utcnow)
    owner:                  str
    tags:                   List[str]                     = Field(default_factory=list)
    archived:               bool                          = False


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTS
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "EntityType", "EventType", "MetricType", "MetricDirection",
    "DimensionType", "ExperimentStatus", "HypothesisConfidence",
    "LearningConfidence", "EvidenceType", "GuardrailSeverity", "GuardrailCondition",
    "Entity", "Event", "Dimension", "Metric", "Segment",
    "Hypothesis", "Exposure", "Guardrail", "Experiment", "Analysis", "Learning",
]
