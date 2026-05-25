from __future__ import annotations

from typing import Dict, List, Optional

from continum.core.semantic_layer.ontology import (
    Metric, MetricDirection, MetricType
)


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
        guardrail_min=0.10,     # hard floor — never let IOR drop below 10%
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
        guardrail_max=0.15,     # hard ceiling — cancellation must not exceed 15%
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
        denominator_event="order_placed",   # 2nd relative to 1st
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


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRY API
# ─────────────────────────────────────────────────────────────────────────────

def get_metric(name: str) -> Metric:
    if name not in METRIC_REGISTRY:
        registered = sorted(METRIC_REGISTRY.keys())
        raise ValueError(
            f"Metric '{name}' is not in the registry.\n"
            f"Register it in metric_registry.py before using it.\n"
            f"Registered metrics: {registered}"
        )
    m = METRIC_REGISTRY[name]
    if m.deprecated:
        replacement = f" Use '{m.superseded_by}' instead." if m.superseded_by else ""
        import warnings
        warnings.warn(f"Metric '{name}' is deprecated.{replacement}", DeprecationWarning, stacklevel=2)
    return m


def register_metric(metric: Metric) -> None:
    if metric.name in METRIC_REGISTRY:
        existing = METRIC_REGISTRY[metric.name]
        if existing.version >= metric.version:
            raise ValueError(
                f"Metric '{metric.name}' v{existing.version} already registered. "
                f"Increment version to replace it."
            )
    METRIC_REGISTRY[metric.name] = metric


def list_metrics(
    owner: Optional[str] = None,
    metric_type: Optional[str] = None,
    include_deprecated: bool = False,
) -> List[Metric]:
    metrics = list(METRIC_REGISTRY.values())
    if not include_deprecated:
        metrics = [m for m in metrics if not m.deprecated]
    if owner:
        metrics = [m for m in metrics if m.owner == owner]
    if metric_type:
        metrics = [m for m in metrics if m.metric_type.value == metric_type]
    return sorted(metrics, key=lambda m: m.name)


def get_guardrail_metrics() -> List[Metric]:
    return [m for m in METRIC_REGISTRY.values()
            if m.guardrail_min is not None or m.guardrail_max is not None]


__all__ = [
    "METRIC_REGISTRY",
    "get_metric",
    "register_metric",
    "list_metrics",
    "get_guardrail_metrics",
]
