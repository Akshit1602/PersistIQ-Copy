"""Intent Analyser — classify a query's intent and extract entities.

Query-understanding layer (extracted from the former runtime.ask.copilot).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("continum.askdata")


# ─────────────────────────────────────────────────────────────────────────────
# TURN — a single conversation exchange
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Turn:
    question: str
    response: str
    intent: str
    entities: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ─────────────────────────────────────────────────────────────────────────────
# INTENT TAXONOMY
# ─────────────────────────────────────────────────────────────────────────────


class Intent:
    WHY_DROPPED = "why_dropped"
    WHY_IMPROVED = "why_improved"
    NEXT_STEP = "next_step"
    SIGNIFICANCE = "significance"
    SEGMENT_EXPLAIN = "segment_explain"
    CAUSAL_EXPLAIN = "causal_explain"
    SUMMARISE = "summarise"
    HEALTH_CHECK = "health_check"
    COMPARE = "compare"
    ANOMALY = "anomaly"
    LEARNINGS = "learnings"
    METRICS = "metrics"
    INVESTIGATE = "investigate"  # recursive drill-down
    COHORT = "cohort"
    ASSUMPTION = "assumption"
    LONGITUDINAL = "longitudinal"
    GENERAL = "general"


_PATTERNS: List[Tuple[str, str]] = [
    (r"why.*(drop|declin|fall|decrease|worse|lower|regress)", Intent.WHY_DROPPED),
    (r"why.*(improv|increas|lift|better|higher|win)", Intent.WHY_IMPROVED),
    (r"(investig|drill|dig|explor|root cause|explain why)", Intent.INVESTIGATE),
    (r"(what.*(next|should|do)|recommend|suggest)", Intent.NEXT_STEP),
    (r"(significant|p.val|stat|result|verdict|ship)", Intent.SIGNIFICANCE),
    (
        r"(segment|cohort|slice|mobile|enterprise|country).*(under|over|worse|better|differ|explain)",
        Intent.SEGMENT_EXPLAIN,
    ),
    (r"(causal|cause|drove|driven|impact|effect|attribut)", Intent.CAUSAL_EXPLAIN),
    (r"(summar|explain|tell me|describe|overview|readout|brief)", Intent.SUMMARISE),
    (r"(health|srm|guardrail|anomal|monitor|ratio)", Intent.HEALTH_CHECK),
    (r"(longitudinal|trend|over time|week.over.week|yoy|past exp)", Intent.LONGITUDINAL),
    (r"(compar|vs\.?|versus|difference|against|side.by.side)", Intent.COMPARE),
    (r"(anomal|outlier|weird|unexpected|strange|spike|dip)", Intent.ANOMALY),
    (r"(learn|histor|previous|before|we ran|last time)", Intent.LEARNINGS),
    (r"(kpi|metric|measure|track|baseline)", Intent.METRICS),
    (r"(cohort|variant|group|arm|assignment|balance)", Intent.COHORT),
    (r"(assum|alpha|power|sample size|threshold|guardrail)", Intent.ASSUMPTION),
]


def detect_intent(question: str) -> str:
    q = question.lower()
    for pattern, intent in _PATTERNS:
        if re.search(pattern, q):
            return intent
    return Intent.GENERAL


# ─────────────────────────────────────────────────────────────────────────────
# ENTITY EXTRACTOR
# Resolves names from free text using the actual metric/dimension registries
# ─────────────────────────────────────────────────────────────────────────────


def extract_entities(question: str) -> Dict[str, Any]:
    q = question.lower()
    entities: Dict[str, Any] = {}

    # Direction
    if re.search(r"drop|declin|fell|worse|lower|regress", q):
        entities["direction"] = "drop"
    elif re.search(r"improv|increas|better|higher|lift|win", q):
        entities["direction"] = "improvement"

    # Metric names — match against registry
    try:
        from continum.datastore.semantic_layer import METRIC_REGISTRY

        matched_metrics = []
        for name, m in METRIC_REGISTRY.items():
            if name.lower() in q or m.display_name.lower() in q:
                matched_metrics.append(name)
            # Also try common abbreviations
            for abbr in [name[:3], name.replace("_", " ")]:
                if abbr in q and name not in matched_metrics:
                    matched_metrics.append(name)
        if matched_metrics:
            entities["metrics"] = matched_metrics
    except Exception:
        pass

    # Segment extraction — match against dimension catalog
    try:
        from continum.datastore.semantic_layer import DIMENSION_CATALOG

        matched_segs = []
        for dim_name, dim in DIMENSION_CATALOG.items():
            # Check if dimension name appears
            if dim_name.lower() in q or dim.display_name.lower() in q:
                matched_segs.append({"dimension": dim_name, "value": None})
            # Check if specific values appear
            if dim.allowed_values:
                for val in dim.allowed_values:
                    if val.lower() in q:
                        matched_segs.append({"dimension": dim_name, "value": val})
            # Check aliases
            if dim.value_aliases:
                for alias, canonical in dim.value_aliases.items():
                    if alias.lower() in q:
                        matched_segs.append({"dimension": dim_name, "value": canonical})
        if matched_segs:
            entities["segments"] = matched_segs
    except Exception:
        # Fallback: regex patterns
        geo = re.search(r"\b(india|us|uk|germany|france|brazil|canada|australia)\b", q)
        if geo:
            entities["segments"] = [{"dimension": "country", "value": geo.group(0)}]
        device = re.search(r"\b(mobile|desktop|tablet|web|ios|android)\b", q)
        if device:
            entities.setdefault("segments", []).append(
                {"dimension": "platform", "value": device.group(0)}
            )

    return entities
