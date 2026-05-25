from __future__ import annotations

from typing import Dict, List, Optional

from continum.core.semantic_layer.ontology import (
    Dimension, DimensionType, EntityType, Segment
)


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
        allowed_values=None,    # open — too many to enumerate
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


# ─────────────────────────────────────────────────────────────────────────────
# SEGMENT LIBRARY
# ─────────────────────────────────────────────────────────────────────────────

SEGMENT_LIBRARY: Dict[str, Segment] = {

    "all_buyers": Segment(
        name="all_buyers",
        description="All buyers in the platform, no filter applied.",
        entity_type=EntityType.BUYER,
        inclusion_predicate="1=1",
        dimensions_used=[],
        owner="analytics_team",
    ),

    "core_accounts": Segment(
        name="core_accounts",
        description="Buyers with account_segment = 'Core'.",
        entity_type=EntityType.ACCOUNT,
        inclusion_predicate="account_segment = 'Core'",
        dimensions_used=["account_segment"],
        owner="analytics_team",
    ),

    "enterprise_accounts": Segment(
        name="enterprise_accounts",
        description="Buyers with account_segment = 'Enterprise'.",
        entity_type=EntityType.ACCOUNT,
        inclusion_predicate="account_segment = 'Enterprise'",
        dimensions_used=["account_segment"],
        owner="analytics_team",
    ),

    "web_buyers": Segment(
        name="web_buyers",
        description="Buyers who primarily access the platform via web.",
        entity_type=EntityType.BUYER,
        inclusion_predicate="platform = 'web'",
        dimensions_used=["platform"],
        owner="product_team",
    ),

    "mobile_buyers": Segment(
        name="mobile_buyers",
        description="Buyers who primarily access the platform via mobile.",
        entity_type=EntityType.BUYER,
        inclusion_predicate="platform = 'mobile'",
        dimensions_used=["platform"],
        owner="product_team",
    ),

    "new_buyers": Segment(
        name="new_buyers",
        description="Buyers who registered within the last 30 days.",
        entity_type=EntityType.BUYER,
        inclusion_predicate="days_since_registration <= 30",
        dimensions_used=[],
        owner="growth_team",
    ),

    "repeat_buyers": Segment(
        name="repeat_buyers",
        description="Buyers with at least 2 completed orders in the last 90 days.",
        entity_type=EntityType.BUYER,
        inclusion_predicate="orders_last_90d >= 2",
        dimensions_used=[],
        owner="growth_team",
    ),

    "high_value_accounts": Segment(
        name="high_value_accounts",
        description="Accounts with total bookings > $10,000 in the last 12 months.",
        entity_type=EntityType.ACCOUNT,
        inclusion_predicate="total_bookings_12m > 10000",
        dimensions_used=[],
        owner="revenue_team",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# CATALOG API
# ─────────────────────────────────────────────────────────────────────────────

def get_dimension(name: str) -> Dimension:
    if name not in DIMENSION_CATALOG:
        raise ValueError(
            f"Dimension '{name}' not in catalog. "
            f"Register it in dimension_catalog.py first."
        )
    return DIMENSION_CATALOG[name]


def get_segment(name: str) -> Segment:
    if name not in SEGMENT_LIBRARY:
        raise ValueError(
            f"Segment '{name}' not in library. "
            f"Register it in dimension_catalog.py first."
        )
    return SEGMENT_LIBRARY[name]


def list_dimensions() -> List[str]:
    return sorted(DIMENSION_CATALOG.keys())


def list_segments(entity_type: Optional[str] = None) -> List[str]:
    if entity_type:
        return sorted(
            k for k, s in SEGMENT_LIBRARY.items()
            if s.entity_type.value == entity_type
        )
    return sorted(SEGMENT_LIBRARY.keys())


def resolve_dimension_value(dim_name: str, raw_value: str) -> str:
    if dim_name not in DIMENSION_CATALOG:
        return raw_value
    return DIMENSION_CATALOG[dim_name].resolve_value(raw_value)


def validate_dimension_value(dim_name: str, value: str) -> bool:
    if dim_name not in DIMENSION_CATALOG:
        return True   # unknown dimension — don't block
    return DIMENSION_CATALOG[dim_name].validate_value(value)


__all__ = [
    "DIMENSION_CATALOG", "SEGMENT_LIBRARY",
    "get_dimension", "get_segment",
    "list_dimensions", "list_segments",
    "resolve_dimension_value", "validate_dimension_value",
]
