from __future__ import annotations
import logging, re, json
from typing import Dict, List, Optional
logger = logging.getLogger("continum.discovery.mapper")

CANONICAL_TABLES = {
    "inquiries":   ["inquiry", "quote", "rfq", "request"],
    "orders":      ["order"],
    "buyers":      ["buyer", "user", "customer", "contact"],
    "accounts":    ["account", "company", "organization", "client"],
    "experiments": ["experiment", "statsig", "ab_test", "variant", "exposure", "assignment"],
    "traffic":     ["traffic", "session", "visit", "pageview"],
}
CANONICAL_COLUMNS = {
    "inquiry_id":         ["inquiry_id", "quote_id", "_id", "id"],
    "buyer_id":           ["buyer_id", "user_id", "user", "customer_id"],
    "account_segment":    ["account_segment", "segment", "business_segment",
                           "consolidated_business_segment"],
    "platform":           ["platform", "device", "channel"],
    "created_at":         ["created_at", "created", "timestamp", "date"],
    "converted_to_order": ["converted_to_order", "converted", "is_order", "ordered"],
    "order_value":        ["order_value", "gmv", "total", "revenue", "aov"],
    "variant":            ["variant", "group_name", "treatment", "arm", "group"],
    "experiment_name":    ["experiment_name", "experiment_id", "test_name", "ab_test"],
    "category":           ["category", "product_category", "process_category"],
    "country":            ["country", "shipping_country", "geo", "region"],
}

def map_tables(table_names: List[str]) -> Dict[str, str]:
    tl = {t.lower(): t for t in table_names}
    mapping = {}
    for canon, keywords in CANONICAL_TABLES.items():
        for kw in keywords:
            for tl_key, orig in tl.items():
                if kw in tl_key:
                    mapping[canon] = orig; break
            if canon in mapping: break
        if canon not in mapping:
            mapping[canon] = ""
    return mapping

def map_columns(profiles: Dict[str, Dict]) -> Dict[str, str]:
    all_cols = set()
    for p in profiles.values():
        all_cols.update(p.get("columns", {}).keys())
    all_cols_lower = {c.lower(): c for c in all_cols}
    mapping = {}
    for canon, keywords in CANONICAL_COLUMNS.items():
        matched = ""
        for kw in keywords:
            if kw in all_cols_lower:
                matched = all_cols_lower[kw]; break
        mapping[canon] = matched
    return mapping

def confidence_score(table_map: Dict, col_map: Dict) -> float:
    t = sum(1 for v in table_map.values() if v) / max(len(table_map), 1)
    c = sum(1 for v in col_map.values() if v) / max(len(col_map), 1)
    return round(0.4 * t + 0.6 * c, 3)

__all__ = ["map_tables", "map_columns", "confidence_score", "CANONICAL_TABLES", "CANONICAL_COLUMNS"]
