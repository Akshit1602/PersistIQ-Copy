"""Semantic layer: ontology models + metric registry + dimension catalog (merged)."""

from __future__ import annotations

# ===== merged from core/semantic_layer/ontology.py =====
import re
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator

# ─────────────────────────────────────────────────────────────────────────────
# ENUMERATIONS
# ─────────────────────────────────────────────────────────────────────────────


class MetricType(str, Enum):
    RATE = "rate"
    MEAN = "mean"
    COUNT = "count"
    SUM = "sum"
    RATIO = "ratio"


class MetricDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    NEUTRAL = "neutral"


class DimensionType(str, Enum):
    CATEGORICAL = "categorical"
    CONTINUOUS = "continuous"
    DATETIME = "datetime"


# ─────────────────────────────────────────────────────────────────────────────
# PRIMITIVE CONCEPTS (consumed by the metric registry + dimension catalog)
# ─────────────────────────────────────────────────────────────────────────────


class Dimension(BaseModel):
    name: str = Field(..., description="snake_case, globally unique")
    display_name: str
    dimension_type: DimensionType
    allowed_values: Optional[List[str]] = None  # None = open-ended
    value_aliases: Dict[str, str] = Field(default_factory=dict)  # "ENT" → "Enterprise"
    owner: str
    version: int = 1
    deprecated: bool = False

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
    name: str = Field(..., description="globally unique, snake_case")
    display_name: str
    description: str
    metric_type: MetricType
    numerator_event: str = Field(..., description="event_type that increments numerator")
    denominator_event: Optional[str] = None  # None for counts/sums
    direction: MetricDirection
    unit: str = Field(..., description="% | $ | count | days | seconds")
    guardrail_min: Optional[float] = None
    guardrail_max: Optional[float] = None
    owner: str
    dependent_dimensions: List[str] = Field(default_factory=list)
    version: int = 1
    deprecated: bool = False
    superseded_by: Optional[str] = None  # metric name if deprecated

    @validator("name")
    def name_must_be_snake_case(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"Metric name must be snake_case, got: {v!r}")
        return v

    class Config:
        frozen = True


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTS
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "MetricType",
    "MetricDirection",
    "DimensionType",
    "Dimension",
    "Metric",
]

# ===== merged from core/semantic_layer/metric_registry.py =====


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

METRIC_REGISTRY: Dict[str, Metric] = {
    "inquiry_order_rate": Metric(
        name="inquiry_order_rate",
        display_name="Inquiry to Order Rate (IOR)",
        description=(
            "Fraction of inquiries (quotes/RFQs) that convert to a placed order. "
            "This is the primary conversion metric for the platform."
        ),
        metric_type=MetricType.RATE,
        numerator_event="order_placed",
        denominator_event="inquiry_created",
        direction=MetricDirection.HIGHER_IS_BETTER,
        unit="%",
        guardrail_min=0.10,  # hard floor — never let IOR drop below 10%
        owner="growth_team",
        dependent_dimensions=["account_segment", "platform", "category"],
    ),
    "avg_order_value": Metric(
        name="avg_order_value",
        display_name="Average Order Value (AOV)",
        description="Mean USD value of placed orders, winsorised at 99th percentile.",
        metric_type=MetricType.MEAN,
        numerator_event="order_placed",
        direction=MetricDirection.HIGHER_IS_BETTER,
        unit="$",
        owner="revenue_team",
        dependent_dimensions=["account_segment", "category", "country"],
    ),
    "revenue_per_inquiry": Metric(
        name="revenue_per_inquiry",
        display_name="Revenue per Inquiry",
        description="IOR × AOV combined signal. Captures both conversion and order size.",
        metric_type=MetricType.RATIO,
        numerator_event="order_placed",
        denominator_event="inquiry_created",
        direction=MetricDirection.HIGHER_IS_BETTER,
        unit="$",
        owner="revenue_team",
        dependent_dimensions=["account_segment", "category"],
    ),
    "quote_to_order_time": Metric(
        name="quote_to_order_time",
        display_name="Quote to Order Time",
        description="Median days between inquiry creation and order placement.",
        metric_type=MetricType.MEAN,
        numerator_event="order_placed",
        denominator_event="inquiry_created",
        direction=MetricDirection.LOWER_IS_BETTER,
        unit="days",
        owner="ops_team",
        dependent_dimensions=["account_segment", "category"],
    ),
    "daily_inquiry_volume": Metric(
        name="daily_inquiry_volume",
        display_name="Daily Inquiry Volume",
        description="Count of new inquiries created per calendar day.",
        metric_type=MetricType.COUNT,
        numerator_event="inquiry_created",
        direction=MetricDirection.HIGHER_IS_BETTER,
        unit="count",
        guardrail_min=0.0,
        owner="ops_team",
        dependent_dimensions=["platform", "category", "country"],
    ),
    "order_cancellation_rate": Metric(
        name="order_cancellation_rate",
        display_name="Order Cancellation Rate",
        description="Fraction of placed orders that are subsequently cancelled.",
        metric_type=MetricType.RATE,
        numerator_event="order_cancelled",
        denominator_event="order_placed",
        direction=MetricDirection.LOWER_IS_BETTER,
        unit="%",
        guardrail_max=0.15,  # hard ceiling — cancellation must not exceed 15%
        owner="ops_team",
        dependent_dimensions=["account_segment", "category"],
    ),
    "new_buyer_activation_rate": Metric(
        name="new_buyer_activation_rate",
        display_name="New Buyer Activation Rate",
        description=(
            "Fraction of newly registered buyers who place at least one order "
            "within 30 days of sign-up."
        ),
        metric_type=MetricType.RATE,
        numerator_event="order_placed",
        denominator_event="buyer_registered",
        direction=MetricDirection.HIGHER_IS_BETTER,
        unit="%",
        owner="growth_team",
        dependent_dimensions=["platform", "country"],
    ),
    "repeat_order_rate": Metric(
        name="repeat_order_rate",
        display_name="Repeat Order Rate",
        description="Fraction of buyers who place a second order within 90 days of their first.",
        metric_type=MetricType.RATE,
        numerator_event="order_placed",
        denominator_event="order_placed",  # 2nd relative to 1st
        direction=MetricDirection.HIGHER_IS_BETTER,
        unit="%",
        owner="growth_team",
        dependent_dimensions=["account_segment"],
    ),
    "checkout_completion_rate": Metric(
        name="checkout_completion_rate",
        display_name="Checkout Completion Rate",
        description="Fraction of buyers who begin checkout and successfully place an order.",
        metric_type=MetricType.RATE,
        numerator_event="order_placed",
        denominator_event="checkout_started",
        direction=MetricDirection.HIGHER_IS_BETTER,
        unit="%",
        owner="product_team",
        dependent_dimensions=["platform", "account_segment"],
    ),
    "session_inquiry_rate": Metric(
        name="session_inquiry_rate",
        display_name="Session to Inquiry Rate",
        description="Fraction of sessions that result in at least one inquiry being created.",
        metric_type=MetricType.RATE,
        numerator_event="inquiry_created",
        denominator_event="session_started",
        direction=MetricDirection.HIGHER_IS_BETTER,
        unit="%",
        owner="product_team",
        dependent_dimensions=["platform"],
    ),
    "feedback_sentiment_score": Metric(
        name="feedback_sentiment_score",
        display_name="Buyer Feedback Sentiment Score",
        description=(
            "Mean NLP compound sentiment score (-1 to +1) across all buyer "
            "feedback submissions in the window."
        ),
        metric_type=MetricType.MEAN,
        numerator_event="feedback_submitted",
        direction=MetricDirection.HIGHER_IS_BETTER,
        unit="score",
        guardrail_min=-0.2,
        owner="cx_team",
    ),
}


__all__ = [
    "METRIC_REGISTRY",
]

# ===== merged from core/semantic_layer/dimension_catalog.py =====


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSION CATALOG
# ─────────────────────────────────────────────────────────────────────────────

DIMENSION_CATALOG: Dict[str, Dimension] = {
    "account_segment": Dimension(
        name="account_segment",
        display_name="Account Segment",
        dimension_type=DimensionType.CATEGORICAL,
        allowed_values=["Individuals", "Core", "Growth", "Enterprise"],
        value_aliases={
            "SMB": "Growth",
            "Medium Business": "Growth",
            "Large Business": "Core",
            "Small Business": "Growth",
            "INDIVIDUAL": "Individuals",
            "ENTERPRISE": "Enterprise",
            "ENT": "Enterprise",
        },
        owner="analytics_team",
    ),
    "platform": Dimension(
        name="platform",
        display_name="Platform",
        dimension_type=DimensionType.CATEGORICAL,
        allowed_values=["web", "mobile", "desktop", "api"],
        value_aliases={
            "WEBAPP": "web",
            "WEB": "web",
            "MOBILE_APP": "mobile",
            "APP": "mobile",
            "FUSION": "desktop",
            "SOLIDWORKS": "desktop",
            "API": "api",
        },
        owner="analytics_team",
    ),
    "country": Dimension(
        name="country",
        display_name="Country",
        dimension_type=DimensionType.CATEGORICAL,
        allowed_values=None,  # open — too many to enumerate
        value_aliases={
            "United States": "US",
            "United Kingdom": "UK",
            "Canada": "CA",
            "Australia": "AU",
            "India": "IN",
        },
        owner="analytics_team",
    ),
    "category": Dimension(
        name="category",
        display_name="Process Category",
        dimension_type=DimensionType.CATEGORICAL,
        allowed_values=["CNC", "Sheet Metal", "FDM", "SLA", "Injection Molding", "Other"],
        value_aliases={},
        owner="catalog_team",
    ),
    "device_type": Dimension(
        name="device_type",
        display_name="Device Type",
        dimension_type=DimensionType.CATEGORICAL,
        allowed_values=["desktop", "mobile", "tablet"],
        value_aliases={
            "DESKTOP": "desktop",
            "MOBILE": "mobile",
            "TABLET": "tablet",
        },
        owner="analytics_team",
    ),
    "price_tier": Dimension(
        name="price_tier",
        display_name="Price Tier",
        dimension_type=DimensionType.CATEGORICAL,
        allowed_values=["low", "mid", "high"],
        value_aliases={},
        owner="revenue_team",
    ),
    "channel": Dimension(
        name="channel",
        display_name="Acquisition Channel",
        dimension_type=DimensionType.CATEGORICAL,
        allowed_values=["organic", "paid", "email", "referral", "direct"],
        value_aliases={
            "ORGANIC": "organic",
            "PAID_SEARCH": "paid",
            "EMAIL": "email",
        },
        owner="marketing_team",
    ),
}


__all__ = [
    "DIMENSION_CATALOG",
]
