from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("continum.intelligence.metric_planner")


# ─────────────────────────────────────────────────────────────────────────────
# METRICS KNOWLEDGE BASE
# ─────────────────────────────────────────────────────────────────────────────

METRICS_KB: Dict[str, Dict] = {
    "acquisition": {
        "primary_pool": [
            "Sign-up completion rate (% of users who start and finish sign-up)",
            "New registered users per day / week",
            "Sign-up-to-first-login rate",
        ],
        "secondary_pool": [
            "Sign-up method distribution (email vs social provider)",
            "Median time to complete sign-up (seconds)",
            "Sign-up page bounce rate",
            "First-session engagement rate",
        ],
        "guardrail_pool": [
            "Email verification completion rate",
            "Sign-up error / dropout rate",
            "Page load time (P95)",
            "Backend error rate",
        ],
        "tracking_event_types": [
            "sign_up_started", "sign_up_step_completed", "sign_up_completed",
            "verification_email_sent", "verification_email_clicked",
            "sign_up_abandoned", "page_load_timing",
        ],
    },
    "conversion": {
        "primary_pool": [
            "Inquiry-to-order rate (IOR) — orders / inquiries",
            "Checkout completion rate — completed checkouts / checkout initiations",
            "Quote acceptance rate — accepted quotes / total quotes",
        ],
        "secondary_pool": [
            "Time from inquiry to order (calendar days)",
            "Quote-to-accept latency (hours)",
            "Checkout step completion rates (per step)",
            "Average order value (AOV) — bookings / orders",
            "Abandonment rate per checkout step",
        ],
        "guardrail_pool": [
            "Order error / payment failure rate",
            "Billing profile completion rate",
            "Quote configuration error rate",
            "Page load time at checkout (P95)",
            "Support ticket rate per order",
        ],
        "tracking_event_types": [
            "checkout_initiated", "checkout_step_completed", "checkout_completed",
            "checkout_abandoned", "payment_submitted", "payment_failed",
            "order_confirmed", "quote_viewed", "quote_accepted",
        ],
    },
    "retention": {
        "primary_pool": [
            "Repeat order rate (% of customers with ≥2 orders in 90 days)",
            "D30 / D60 / D90 retention rate",
            "Monthly active buyers (MAB)",
        ],
        "secondary_pool": [
            "Median days between orders",
            "Average orders per buyer per quarter",
            "Churn rate (no order in 90 days after last order)",
            "Reactivation rate (churned users who return)",
        ],
        "guardrail_pool": [
            "Unsubscribe / opt-out rate (emails)",
            "First-order-to-second-order conversion rate",
            "NPS / CSAT score",
            "Customer support ticket volume",
        ],
        "tracking_event_types": [
            "repeat_order_placed", "loyalty_nudge_sent", "loyalty_nudge_clicked",
            "user_churned", "user_reactivated", "order_completed",
        ],
    },
    "engagement": {
        "primary_pool": [
            "Feature adoption rate (% of eligible users who use the feature)",
            "Daily active users (DAU) or weekly active users (WAU)",
            "Session depth (pages / actions per session)",
        ],
        "secondary_pool": [
            "Feature engagement rate (% of sessions with ≥1 feature interaction)",
            "Median session duration",
            "Click-through rate on key CTAs",
            "Return visits per user per week",
        ],
        "guardrail_pool": [
            "Page load time (P95 ms)",
            "JavaScript error rate",
            "Overall bounce rate",
            "Task success rate on critical flows",
        ],
        "tracking_event_types": [
            "feature_viewed", "feature_interaction", "cta_clicked",
            "session_started", "session_ended", "page_viewed",
            "error_encountered",
        ],
    },
    "pricing": {
        "primary_pool": [
            "IOR — inquiry-to-order rate",
            "Average order value (AOV)",
            "Revenue per visitor (RPV = orders × AOV / visitors)",
        ],
        "secondary_pool": [
            "Price tier selection distribution",
            "Quote-to-order time (days)",
            "Discount usage rate",
            "Cart abandonment at pricing step",
        ],
        "guardrail_pool": [
            "Gross margin per order",
            "Refund / cancellation rate",
            "Support escalation rate",
            "Net revenue per cohort",
        ],
        "tracking_event_types": [
            "price_tier_viewed", "price_tier_selected", "price_comparison_expanded",
            "checkout_initiated", "order_confirmed", "discount_applied",
        ],
    },
}


_CARD_FORMAT_REMINDER = (
    "\nFORMAT RULES:\n"
    "- Use 'Field: value' on each line — no markdown, no bullets, no headers\n"
    "- Separate metrics with ONE blank line\n"
    "- No preamble, no sign-off\n"
)

_SECTION_SYSTEM = (
    "You are a senior product analytics expert who writes precise, "
    "implementation-ready experiment measurement plans. "
    "Be specific — use actual column names and metric definitions. "
    "Never use vague language like 'monitor the impact'. "
    "Always include exact numerators and denominators."
)


# ─────────────────────────────────────────────────────────────────────────────
# LLM CALL WRAPPER (with structured fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _call_section(llm, section_name: str, prompt: str,
                  fallback: str, max_tokens: int = 480) -> str:
    if llm is None:
        return fallback
    try:
        return str(llm.ask(prompt))
    except Exception as e:
        logger.warning("%s LLM call failed (%s) — using fallback", section_name, e)
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# KPI CONFIG INFERENCE
# ─────────────────────────────────────────────────────────────────────────────

def infer_kpi_config(desc: str, llm=None) -> Tuple[str, str, str, List[str]]:
    defaults = ("iteration", "partial", "balanced", ["maturity", "instrumentation", "preference"])
    if llm is None:
        return defaults

    prompt = (
        f'Feature: "{desc}"\n\n'
        "Infer the KPI planning configuration. Return ONLY valid JSON — no other text:\n"
        '{\n'
        '  "maturity": "mvp" | "iteration" | "critical",\n'
        '  "instrumentation": "none" | "partial" | "full",\n'
        '  "preference": "leading" | "balanced" | "lagging",\n'
        '  "uncertain": ["maturity"]\n'
        '}\n'
        "maturity=mvp if first launch. instrumentation=full if v2/existing. "
        "preference=lagging if revenue/conversion explicitly mentioned. "
        "uncertain lists only keys that are genuinely ambiguous (1-2 max)."
    )
    try:
        raw = llm.ask(prompt)
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            d = json.loads(m.group())
            maturity        = d.get("maturity",        "iteration")
            instrumentation = d.get("instrumentation", "partial")
            preference      = d.get("preference",      "balanced")
            uncertain       = d.get("uncertain",       [])
            if maturity        not in {"mvp", "iteration", "critical"}:   maturity = "iteration"
            if instrumentation not in {"none", "partial", "full"}:        instrumentation = "partial"
            if preference      not in {"leading", "balanced", "lagging"}: preference = "balanced"
            return maturity, instrumentation, preference, uncertain
    except Exception as e:
        logger.warning("infer_kpi_config failed: %s", e)
    return defaults


def confirm_uncertain(
    config: Dict[str, str],
    uncertain: List[str],
    config_options: Dict[str, Any],
) -> Dict[str, str]:
    if not uncertain:
        return config
    print(f"\n  Confirming {len(uncertain)} inferred value(s) — press Enter to accept:\n")
    for key in uncertain:
        if key not in config_options:
            continue
        valid_vals, display_map = config_options[key]
        default = config.get(key, valid_vals[0])
        choices = "/".join(f"[{v}]" if v == default else v for v in valid_vals)
        raw = input(f"  ❓ {key.replace('_',' ').title()} ({choices}): ").strip().lower()
        if raw and raw in valid_vals:
            config[key] = raw
    return config


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRAINT INFERENCE (causal method selection)
# ─────────────────────────────────────────────────────────────────────────────

def infer_constraints_from_description(desc: str, llm=None) -> Tuple[Dict, List[str]]:
    defaults: Dict = {
        "can_randomise":    True,
        "rollout_pct":      50,
        "has_control_group": False,
        "has_time_series":  True,
        "pre_period_days":  180,
        "observational":    False,
        "has_threshold":    False,
    }
    if llm is None:
        return defaults, list(defaults.keys())

    prompt = (
        f'A product team wants to test this feature: "{desc}"\n\n'
        "Infer the experiment setup constraints. Reply ONLY with valid JSON:\n"
        "{\n"
        '  "can_randomise": true,\n'
        '  "rollout_pct": 50,\n'
        '  "has_control_group": false,\n'
        '  "has_time_series": true,\n'
        '  "pre_period_days": 180,\n'
        '  "observational": false,\n'
        '  "has_threshold": false,\n'
        '  "uncertain_keys": ["rollout_pct"]\n'
        "}\n"
        "uncertain_keys lists the 1-3 keys most worth confirming with the user."
    )
    try:
        raw = llm.ask(prompt)
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            d = json.loads(m.group())
            uncertain = d.pop("uncertain_keys", [])
            for k, v in defaults.items():
                d.setdefault(k, v)
            return d, uncertain
    except Exception as e:
        logger.warning("infer_constraints_from_description failed: %s", e)
    return defaults, list(defaults.keys())


def confirm_uncertain_constraints(constraints: Dict, uncertain: List[str]) -> Dict:
    QUESTION_MAP = {
        "can_randomise":     ("Can users be randomly assigned to control vs treatment?", bool),
        "rollout_pct":       ("% of traffic receiving this feature (100 = full rollout)?", float),
        "has_control_group": ("Will there be a permanent untreated group?", bool),
        "has_time_series":   ("Do you have 3+ months of historical daily data?", bool),
        "pre_period_days":   ("How many days of pre-feature history are available?", int),
        "observational":     ("Observational study — users self-select rather than being assigned?", bool),
        "has_threshold":     ("Is treatment assigned based on a score or threshold?", bool),
    }
    if not uncertain:
        return constraints
    print(f"\n  Confirming {len(uncertain)} inferred value(s) — press Enter to accept:\n")
    for key in uncertain:
        if key not in QUESTION_MAP:
            continue
        q, typ = QUESTION_MAP[key]
        default = constraints.get(key)
        if typ == bool:
            hint = f"[{'Y/n' if default else 'y/N'}]"
            raw = input(f"  ❓ {q} {hint}: ").strip().lower()
            if raw:
                constraints[key] = raw in ("y", "yes")
        elif typ in (float, int):
            hint = f"[{default}]"
            raw = input(f"  ❓ {q} {hint}: ").strip()
            if raw:
                try:
                    constraints[key] = typ(raw)
                except ValueError:
                    pass
    return constraints


# ─────────────────────────────────────────────────────────────────────────────
# METRIC SECTION GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def _get_kb(category: str) -> Dict:
    return METRICS_KB.get(category, METRICS_KB["conversion"])


def gen_primary_metrics(
    desc: str, category: str, maturity: str = "iteration",
    preference: str = "balanced", llm=None,
) -> str:
    kb         = _get_kb(category)
    candidates = "\n".join(f"- {m}" for m in kb["primary_pool"])
    pref_note  = {
        "leading":  "Prefer early-signal leading indicators.",
        "balanced": "Include one leading indicator and one lagging revenue outcome.",
        "lagging":  "Focus on revenue-tied lagging outcomes (conversion rate, AOV, GMV).",
    }.get(preference, "")
    prompt = (
        f"Feature: {desc}\nFunnel stage: {category}\nMaturity: {maturity}\n\n"
        f"Candidate primary metrics:\n{candidates}\n\n{pref_note}\n\n"
        "Choose 2-3 of the most relevant primary metrics. For each:\n"
        "Metric: <name>\nDefinition: <exact numerator/denominator>\n"
        "Why primary: <one sentence>\nExpected direction: Increase or Decrease\n"
        f"Expected magnitude: <realistic range>\n{_CARD_FORMAT_REMINDER}"
    )
    fallback = "\n\n".join(
        f"Metric: {m}\nDefinition: {m}\nWhy primary: Core conversion signal.\n"
        "Expected direction: Increase\nExpected magnitude: +5-10% relative"
        for m in kb["primary_pool"][:2]
    )
    return _call_section(llm, "PRIMARY METRICS", prompt, fallback)


def gen_secondary_metrics(
    desc: str, category: str, llm=None,
) -> str:
    kb         = _get_kb(category)
    candidates = "\n".join(f"- {m}" for m in kb["secondary_pool"])
    prompt = (
        f"Feature: {desc}\nFunnel stage: {category}\n\n"
        f"Candidate secondary metrics:\n{candidates}\n\n"
        "Choose 3-4 diagnostic metrics. For each:\n"
        "Metric: <name>\nDefinition: <exact measurement>\n"
        f"Why secondary: <diagnostic signal>\nExpected direction: Increase or Decrease or Neutral\n"
        f"Expected magnitude: <realistic expectation>\n{_CARD_FORMAT_REMINDER}"
    )
    fallback = "\n\n".join(
        f"Metric: {m}\nDefinition: {m}\nWhy secondary: Diagnostic signal.\n"
        "Expected direction: Neutral\nExpected magnitude: Monitoring only"
        for m in kb["secondary_pool"][:3]
    )
    return _call_section(llm, "SECONDARY METRICS", prompt, fallback)


def gen_guardrail_metrics(
    desc: str, category: str, maturity: str = "iteration", llm=None,
) -> str:
    kb         = _get_kb(category)
    candidates = "\n".join(f"- {m}" for m in kb["guardrail_pool"])
    threshold_map = {"mvp": "5-10%", "iteration": "2-3%", "critical": "0.5-1%"}
    threshold = threshold_map.get(maturity, "3-5%")
    prompt = (
        f"Feature: {desc}\nFunnel stage: {category}\nMaturity: {maturity} (threshold: {threshold})\n\n"
        f"Candidate guardrail metrics:\n{candidates}\n\n"
        "List ALL relevant guardrail metrics. For each:\n"
        "Metric: <name>\nDefinition: <exact measurement>\n"
        f"Risk: <why degradation is dangerous>\n"
        f"Threshold: Must not degrade by more than {threshold} — halt if breached.\n"
        f"Expected direction: Neutral (must not worsen)\n{_CARD_FORMAT_REMINDER}"
    )
    fallback = "\n\n".join(
        f"Metric: {m}\nDefinition: {m}\nRisk: Critical no-harm metric.\n"
        f"Threshold: Must not degrade by more than {threshold}.\n"
        "Expected direction: Neutral"
        for m in kb["guardrail_pool"][:2]
    )
    return _call_section(llm, "GUARDRAIL METRICS", prompt, fallback)


def gen_tracking_requirements(
    desc: str, category: str, instrumentation: str = "partial", llm=None,
) -> str:
    kb = _get_kb(category)
    depth_map = {
        "none":    "6-10 concrete tracking events covering the full user path.",
        "partial": "4-6 NEW events specific to this feature.",
        "full":    "2-3 events maximum. Focus on extending existing events.",
    }
    depth_note  = depth_map.get(instrumentation, "4-6 events")
    event_types = "\n".join(f"- {e}" for e in kb["tracking_event_types"])
    prompt = (
        f"Feature: {desc}\nFunnel stage: {category}\nInstrumentation: {instrumentation} ({depth_note})\n\n"
        f"Relevant tracking event types:\n{event_types}\n\n"
        "For each event:\n"
        "Track: <snake_case_event_name>\n"
        "When: <exact user action or system event>\n"
        "Properties: user_id (string), timestamp (datetime), feature_variant (string), <specific props>\n"
        "Why needed: <which metric this enables>\n"
        "Separate events with ONE blank line. No markdown. No bullets."
    )
    fallback = "\n\n".join(
        f"Track: {e}\nWhen: User triggers {e.replace('_', ' ')}.\n"
        "Properties: user_id (string), timestamp (datetime), feature_variant (string)\n"
        "Why needed: Core funnel tracking."
        for e in kb["tracking_event_types"][:3]
    )
    return _call_section(llm, "DATA TRACKING REQUIREMENTS", prompt, fallback)


def gen_open_questions(desc: str, category: str, llm=None) -> str:
    prompt = (
        f"Feature: {desc}\nFunnel stage: {category}\n\n"
        "List 4-5 specific open questions to resolve BEFORE launch.\n"
        "Focus on: baseline stability, event name collisions, segment scope, "
        "holdout group design, power calculation inputs, data quality.\n"
        "Write each question on its own line starting with a number.\n"
        "Make each concrete and specific to this feature."
    )
    fallback = (
        "1. Confirm baseline rate stability across weekdays for the past 30 days.\n"
        "2. Verify proposed event names do not collide with existing analytics events.\n"
        "3. Identify which user segments should be excluded (staff, bots, internal).\n"
        "4. Confirm assignment unit (user vs session) and stickiness requirements.\n"
        "5. Validate minimum detectable effect aligns with product team's business case."
    )
    return _call_section(llm, "OPEN QUESTIONS & ASSUMPTIONS", prompt, fallback)


def gen_metrics_bundle(
    desc: str,
    category: str,
    maturity: str = "iteration",
    preference: str = "balanced",
    instrumentation: str = "partial",
    llm=None,
) -> Dict[str, str]:
    kb         = _get_kb(category)
    threshold  = {"mvp": "5-10%", "iteration": "2-3%", "critical": "0.5-1%"}.get(maturity, "3-5%")
    pref_note  = {
        "leading":  "Prefer early-signal leading indicators for primary.",
        "balanced": "Include one leading and one lagging metric for primary.",
        "lagging":  "Focus on revenue-tied lagging outcomes for primary.",
    }.get(preference, "")

    p_cands = "\n".join(f"- {m}" for m in kb["primary_pool"])
    s_cands = "\n".join(f"- {m}" for m in kb["secondary_pool"])
    g_cands = "\n".join(f"- {m}" for m in kb["guardrail_pool"])

    prompt = (
        f"Feature: {desc}\nFunnel stage: {category}\n"
        f"Maturity: {maturity} — guardrail threshold: {threshold}\n{pref_note}\n\n"
        "Generate THREE sections. Each header in UPPERCASE. Use 'Field: value' lines only.\n\n"
        f"PRIMARY METRICS\nChoose 2-3 from:\n{p_cands}\n"
        "For each: Metric: / Definition: / Why primary: / Expected direction: / Expected magnitude:\n\n"
        f"SECONDARY METRICS\nChoose 3-4 from:\n{s_cands}\n"
        "For each: Metric: / Definition: / Why secondary: / Expected direction:\n\n"
        f"GUARDRAIL METRICS\nChoose all relevant from:\n{g_cands}\n"
        f"For each: Metric: / Definition: / Risk: / Threshold: Must not degrade by more than {threshold}.\n"
        "\nStart immediately with PRIMARY METRICS — no other text."
    )

    raw = ""
    if llm is not None:
        try:
            raw = llm.ask(prompt)
        except Exception as e:
            logger.warning("gen_metrics_bundle LLM call failed: %s", e)

    # Parse sections from output
    sections: Dict[str, str] = {}
    for header in ("PRIMARY METRICS", "SECONDARY METRICS", "GUARDRAIL METRICS"):
        m = re.search(
            rf"{re.escape(header)}\s*\n(.*?)(?=(?:PRIMARY METRICS|SECONDARY METRICS|GUARDRAIL METRICS)|\Z)",
            raw, re.DOTALL | re.IGNORECASE,
        )
        sections[header] = m.group(1).strip() if m else ""

    # Validate and fallback
    fallback_fns = {
        "PRIMARY METRICS":   lambda: gen_primary_metrics(desc, category, maturity, preference, None),
        "SECONDARY METRICS": lambda: gen_secondary_metrics(desc, category, None),
        "GUARDRAIL METRICS": lambda: gen_guardrail_metrics(desc, category, maturity, None),
    }
    result: Dict[str, str] = {}
    for name, fn in fallback_fns.items():
        content    = sections.get(name, "").strip()
        field_hits = len(re.findall(r"^(?:Metric|Definition|Why|Expected|Risk|Threshold):",
                                    content, re.MULTILINE | re.IGNORECASE))
        if not content or field_hits < 2:
            logger.info("Structured fallback applied for %s", name)
            result[name] = fn()
        else:
            result[name] = content

    result["DATA TRACKING REQUIREMENTS"] = gen_tracking_requirements(
        desc, category, instrumentation, llm)
    result["OPEN QUESTIONS & ASSUMPTIONS"] = gen_open_questions(desc, category, llm)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# PAST LEARNINGS FORMATTER
# ─────────────────────────────────────────────────────────────────────────────

def format_past_learnings(learnings: List[Dict]) -> str:
    if not learnings:
        return "No relevant past experiments found."
    lines = []
    for L in learnings:
        lines.append(
            f"• {L.get('experiment_name', '?')} ({L.get('ship_decision', '?')}): "
            f"{L.get('outcome', '')}"
        )
        if L.get("key_learning"):
            lines.append(f"  Key learning: {L['key_learning']}")
        if L.get("recommendation"):
            lines.append(f"  Recommendation: {L['recommendation']}")
    return "\n".join(lines)


__all__ = [
    "METRICS_KB",
    "infer_kpi_config",
    "confirm_uncertain",
    "infer_constraints_from_description",
    "confirm_uncertain_constraints",
    "gen_primary_metrics",
    "gen_secondary_metrics",
    "gen_guardrail_metrics",
    "gen_tracking_requirements",
    "gen_open_questions",
    "gen_metrics_bundle",
    "format_past_learnings",
]
