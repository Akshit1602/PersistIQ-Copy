"""Intent — classify a chatbot message's intent and extract entities.

Query-understanding layer, used only on the chatbot path (manual experiment
usage routes straight to the relevant ExpSuite module, bypassing this file).
``analyse()`` is the LLM-backed entry point; the regex-based ``detect_intent``/
``extract_entities`` below it are its deterministic, no-LLM fallback.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("continum.orchestration.intent")


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
        from continum.ContextGraph.semantic_layer import METRIC_REGISTRY

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
        from continum.ContextGraph.semantic_layer import DIMENSION_CATALOG

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


# ─────────────────────────────────────────────────────────────────────────────
# LLM ANALYSIS — the chatbot-path entry point
# Breaks a free-text message down into what the user wants done, so the
# orchestrator can route it. Falls back to the regex layer above with no LLM.
# ─────────────────────────────────────────────────────────────────────────────


def analyse(question: str, llm=None) -> Dict[str, Any]:
    """Understand a chatbot message: what task is expected.

    Returns ``{intent, entities, task_kind, needs_visual, refined}`` where
    ``task_kind`` is one of ``data`` (AskData NL→SQL), ``analysis`` (an ExpSuite
    module), or ``guide`` (how-to / about). Used ONLY on the chatbot path — manual
    experiment usage is routed directly to the relevant ExpSuite module.
    """
    q = (question or "").strip()
    base = {
        "intent": detect_intent(q),
        "entities": extract_entities(q),
        "task_kind": "data",
        "needs_visual": bool(
            re.search(r"\b(chart|plot|graph|trend|visuali[sz]e|over time|by )\b", q, re.I)
        ),
        "refined": q,
    }
    if llm is None:
        try:
            from continum import get_llm

            llm = get_llm()
        except Exception:  # noqa: BLE001
            llm = None
    if llm is None or not getattr(llm, "is_loaded", False):
        return base  # deterministic fallback (no LLM configured)

    prompt = (
        "Classify this analytics assistant message. Return ONLY JSON with keys: "
        "'task_kind' (data|analysis|guide), 'needs_visual' (true/false), "
        "'refined' (a self-contained rephrasing).\n\n"
        "- data: a question answerable by querying the dataset (NL->SQL).\n"
        "- analysis: needs an experimentation module (causal, health, power, audience, readout...).\n"
        "- guide: how-to / what-is / about-the-tool.\n\n"
        f"Message: {q}"
    )
    try:
        import json

        raw = llm.ask(prompt) if hasattr(llm, "ask") else str(llm.invoke(prompt).content)
        raw = raw.strip()
        if "```" in raw:
            raw = (
                raw.split("```json")[-1].split("```")[0].strip()
                if "```json" in raw
                else raw.replace("```", "").strip()
            )
        data = json.loads(raw)
        base["task_kind"] = data.get("task_kind", base["task_kind"])
        base["needs_visual"] = bool(data.get("needs_visual", base["needs_visual"]))
        base["refined"] = data.get("refined") or q
    except Exception:  # noqa: BLE001 — keep the deterministic base on any parse error
        pass
    return base


__all__ = ["Turn", "Intent", "detect_intent", "extract_entities", "analyse"]
