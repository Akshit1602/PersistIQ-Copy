from typing import List
from pydantic import BaseModel, Field


class MetricPlannerInput(BaseModel):
    primary_metric: str = Field(..., description="Target primary metric e.g. 'cart_conversion_rate'")
    retail_domain: str = Field("checkout", description="Retail domain area e.g. 'checkout', 'pdp', 'search'")


class MetricPlanResult(BaseModel):
    primary_metric: str
    recommended_guardrails: List[str]
    recommended_secondary: List[str]
    summary: str


# Heuristic mapping for retail experimentation guardrails
RETAIL_GUARDRAIL_MAP = {
    "checkout": ["checkout_error_rate", "page_latency_ms", "order_cancellation_rate"],
    "pdp": ["bounce_rate", "add_to_cart_latency_ms", "return_rate"],
    "cart": ["cart_abandonment_rate", "promo_code_failure_rate"],
    "search": ["zero_result_search_rate", "filter_reset_rate"]
}

RETAIL_SECONDARY_MAP = {
    "checkout": ["average_order_value", "units_per_transaction"],
    "pdp": ["cart_add_rate", "image_gallery_interaction_rate"],
    "cart": ["cross_sell_click_through_rate", "average_order_value"],
    "search": ["search_to_pdp_click_rate", "search_conversion_rate"]
}


def plan_experiment_metrics(input_data: MetricPlannerInput) -> MetricPlanResult:
    """
    Selects guardrail and secondary metrics based on the domain and primary metric.
    """
    domain = input_data.retail_domain.lower()
    guardrails = RETAIL_GUARDRAIL_MAP.get(domain, ["page_latency_ms", "error_rate"])
    secondary = RETAIL_SECONDARY_MAP.get(domain, ["average_order_value"])

    summary = (
        f"Metric Plan for '{input_data.primary_metric}' ({input_data.retail_domain.upper()}): "
        f"Mapped {len(guardrails)} guardrail metrics ({', '.join(guardrails)}) "
        f"and {len(secondary)} secondary metrics ({', '.join(secondary)})."
    )

    return MetricPlanResult(
        primary_metric=input_data.primary_metric,
        recommended_guardrails=guardrails,
        recommended_secondary=secondary,
        summary=summary
    )