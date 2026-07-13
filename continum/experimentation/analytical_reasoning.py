from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger("continum.intelligence.analytical_reasoning")


# ─────────────────────────────────────────────────────────────────────────────
# ADDITIONAL INSIGHT MINING
# ─────────────────────────────────────────────────────────────────────────────


def mine_additional_insights(
    df: pd.DataFrame,
    control: str = "control",
    treatment: str = "treatment",
    date_col: str = "created_at",
    outcome_col: str = "converted_to_order",
    value_col: str = "order_value",
) -> Dict:
    results: Dict = {}

    # ── 1. Time-period decay ─────────────────────────────────────────────────
    try:
        data = df.copy()
        data[date_col] = pd.to_datetime(data[date_col])
        mid = data[date_col].min() + (data[date_col].max() - data[date_col].min()) / 2
        early = data[data[date_col] <= mid]
        late = data[data[date_col] > mid]

        def _delta(frame):
            c = frame[frame["variant"] == control][outcome_col].mean()
            t = frame[frame["variant"] == treatment][outcome_col].mean()
            nc = len(frame[frame["variant"] == control])
            nt = len(frame[frame["variant"] == treatment])
            return ((float(t) - float(c)) * 100, nc, nt) if nc >= 30 and nt >= 30 else (None, 0, 0)

        e_d, *_ = _delta(early)
        l_d, *_ = _delta(late)
        if e_d is not None and l_d is not None:
            decay = l_d - e_d
            direction = (
                "weakening" if decay < -0.3 else "strengthening" if decay > 0.3 else "stable"
            )
            results["time_decay"] = {
                "early_delta_pp": round(e_d, 3),
                "late_delta_pp": round(l_d, 3),
                "decay_pp": round(decay, 3),
                "decay_direction": direction,
                "summary": (f"Early-half Δ={e_d:+.2f}pp → Late-half Δ={l_d:+.2f}pp ({direction})"),
            }
    except Exception as e:
        logger.debug("Time decay mining failed: %s", e)

    # ── 2. Cohort effect ─────────────────────────────────────────────────────
    try:
        if "lifetime_orders" in df.columns:
            df["_new"] = df["lifetime_orders"].fillna(0) <= 1
            new_df = df[df["_new"]]
            ret_df = df[~df["_new"]]

            def _seg_delta(frame):
                c = frame[frame["variant"] == control][outcome_col].mean()
                t = frame[frame["variant"] == treatment][outcome_col].mean()
                nc = len(frame[frame["variant"] == control])
                nt = len(frame[frame["variant"] == treatment])
                return ((float(t) - float(c)) * 100, nt) if nc >= 30 and nt >= 30 else (None, 0)

            nd, nn = _seg_delta(new_df)
            rd, rn = _seg_delta(ret_df)
            if nd is not None and rd is not None:
                results["cohort_effect"] = {
                    "new_user_delta_pp": round(nd, 3),
                    "returning_user_delta_pp": round(rd, 3),
                    "divergence": abs(nd - rd) > 0.5,
                    "summary": (
                        f"New users Δ={nd:+.2f}pp (n={nn:,}) vs "
                        f"returning Δ={rd:+.2f}pp (n={rn:,}) "
                        f"{'— DIVERGENT' if abs(nd-rd) > 0.5 else '— similar response'}"
                    ),
                }
    except Exception as e:
        logger.debug("Cohort effect mining failed: %s", e)

    # ── 3. Cross-metric ──────────────────────────────────────────────────────
    try:
        if value_col in df.columns:
            ctrl_conv = df[(df["variant"] == control) & (df[outcome_col] == 1)]
            trt_conv = df[(df["variant"] == treatment) & (df[outcome_col] == 1)]
            if len(ctrl_conv) >= 30 and len(trt_conv) >= 30:
                aov_c = float(ctrl_conv[value_col].mean())
                aov_t = float(trt_conv[value_col].mean())
                delta = (aov_t - aov_c) / aov_c * 100 if aov_c > 0 else 0
                results["cross_metric"] = {
                    "aov_control": round(aov_c, 2),
                    "aov_treatment": round(aov_t, 2),
                    "aov_delta_pct": round(delta, 2),
                    "aligned": (delta > 1)
                    == (results.get("time_decay", {}).get("late_delta_pp", 0) > 0),
                    "summary": (
                        f"AOV: ${aov_c:.0f} → ${aov_t:.0f} ({delta:+.1f}%) "
                        f"{'— aligned with IOR direction' if delta * (aov_t - aov_c) >= 0 else '— IOR and AOV DIVERGE (investigate)'}"
                    ),
                }
    except Exception as e:
        logger.debug("Cross-metric mining failed: %s", e)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# UNIFIED SYNTHESIS PROMPT
# ─────────────────────────────────────────────────────────────────────────────


def synthesise_findings(
    context: Dict,
    llm: Any = None,
) -> str:
    if llm is None:
        # Template fallback
        overall = context.get("overall_summary", "")
        seg = context.get("segment_summary", "No segment breakdown.")
        decision = context.get("decision", "unknown")
        return (
            f"SYNTHESIS:\n{overall}. {seg}\n\n"
            f"IMPLICATIONS:\nDecision: {decision}. "
            "Proceed according to recommendation.\n\n"
            "TRADE-OFFS:\nSee segment-level results for nuance.\n\n"
            "KNOWLEDGE APPLIED:\nNo prior learnings retrieved."
        )

    prompt = f"""You are a senior product analytics lead synthesising a concluded experiment.

EXPERIMENT: {context.get('experiment', '')}
DESCRIPTION: {context.get('description', '')}
HYPOTHESIS: {context.get('hypothesis', '(not recorded)')}
TEAM: {context.get('team', '')}

STATISTICAL RESULTS:
  Overall: {context.get('overall_summary', '')}
  Key segments: {context.get('segment_summary', 'None')}
  Interesting findings: {context.get('interesting_summary', 'None')}
  Time trend: {context.get('time_trend_summary', 'Not computed')}
  Additional insights: {context.get('extra_insights', 'None')}

DECISION: {context.get('decision', 'unknown')}
REASONING: {context.get('reasoning', '')}

RELEVANT PAST EXPERIMENTS ({context.get('n_past_learnings', 0)} found):
{context.get('past_learnings', '(None)')}

Write EXACTLY FOUR sections:

SYNTHESIS:
3-4 sentences combining stats, segments, and time trend. Reconcile tensions. Be specific — reference numbers.

IMPLICATIONS:
3-4 bullets: who gets the feature, rollout sequence, risks to monitor, expected 90-day impact.

TRADE-OFFS:
2-3 bullets: what we give up with this decision. Be honest and specific.

KNOWLEDGE APPLIED:
1-2 sentences on what past experiments informed this interpretation.

Plain business English. No emojis."""

    try:
        return str(llm.ask(prompt))
    except Exception as e:
        logger.warning("synthesise_findings LLM failed: %s", e)
        return f"(Synthesis unavailable: {e})"


# ─────────────────────────────────────────────────────────────────────────────
# ROOT-CAUSE SYNTHESIS
# ─────────────────────────────────────────────────────────────────────────────


def generate_root_cause(
    anomalies: List[Dict],
    experiment: str = "",
    data_context: Dict = None,
    llm: Any = None,
) -> str:
    if not anomalies:
        return "No anomalies to explain."

    ctx = data_context or {}
    anomaly_text = "\n".join(
        f"  - [{a.get('severity','?').upper()}] {a.get('metric','?')}: "
        f"{a.get('type','?')} z={a.get('z_score','?')} "
        f"value={a.get('value','?')} baseline={a.get('baseline','?')}"
        for a in anomalies[:8]
    )

    pipeline_state = ctx.get("pipeline_health", "unknown")
    running_exps = ctx.get("running_experiments", [])
    exp_text = ", ".join(e.get("name", str(e)) for e in running_exps[:3]) or "none identified"

    if llm is None:
        parts = [f"{a.get('metric','?')} {a.get('type','?')}" for a in anomalies[:3]]
        return (
            f"Root-cause candidates for anomalies in {experiment or 'current window'}:\n"
            f"  1. Experiment effect from: {exp_text}\n"
            f"  2. Data pipeline issue (pipeline health: {pipeline_state})\n"
            f"  3. Seasonal / external factor\n"
            f"  Affected metrics: {', '.join(parts)}"
        )

    prompt = f"""You are a senior data engineer diagnosing anomalies in a live experiment platform.

Experiment: {experiment or 'platform-wide'}
Anomalies detected:
{anomaly_text}

Running experiments: {exp_text}
Pipeline health: {pipeline_state}

In 3-5 sentences:
1. What is the most likely root cause for each major anomaly?
2. Distinguish: experiment effect vs data pipeline issue vs genuine business change.
3. What single investigation action should happen in the next 30 minutes?

Be specific. Avoid generic advice. No emojis."""

    try:
        return str(llm.ask(prompt))
    except Exception as e:
        return f"(Root-cause analysis unavailable: {e})"


# ─────────────────────────────────────────────────────────────────────────────
# ADAPTIVE RECOMMENDATIONS
# ─────────────────────────────────────────────────────────────────────────────

_RECOMMENDATION_RULES: Dict[str, List[Dict]] = {
    "experiment_not_significant": [
        {
            "action": "Extend experiment",
            "reason": "p-value not reached — need more data",
            "module": "power_calculator",
            "priority": 1,
        },
        {
            "action": "Check guardrails",
            "reason": "Ensure no degradation while waiting",
            "module": "health_monitor",
            "priority": 2,
        },
    ],
    "experiment_significant_ship": [
        {
            "action": "Measure ROI post-ship",
            "reason": "Validate lift holds in production",
            "module": "roi_tracker",
            "priority": 1,
        },
        {
            "action": "Run causal analysis",
            "reason": "Strengthen attribution before scaling",
            "module": "causal_analysis",
            "priority": 2,
        },
    ],
    "experiment_significant_no_ship": [
        {
            "action": "Investigate segment divergence",
            "reason": "Understand why result is negative",
            "module": "simpsons_paradox",
            "priority": 1,
        },
        {
            "action": "Run causal analysis",
            "reason": "Confirm the effect isn't confounded",
            "module": "causal_analysis",
            "priority": 2,
        },
    ],
    "srm_detected": [
        {
            "action": "Pause experiment",
            "reason": "SRM invalidates statistical inference",
            "module": "health_monitor",
            "priority": 0,
        },
        {
            "action": "Investigate assignment logic",
            "reason": "Find the SRM root cause",
            "module": "data_validation",
            "priority": 1,
        },
    ],
    "simpsons_paradox_detected": [
        {
            "action": "Stratify analysis by confounding dimension",
            "reason": "Aggregate direction misleading",
            "module": "causal_analysis",
            "priority": 1,
        },
        {
            "action": "Consider segment-specific rollout",
            "reason": "Ship only to segments with positive effect",
            "module": "audience_selection",
            "priority": 2,
        },
    ],
    "low_power": [
        {
            "action": "Increase traffic allocation",
            "reason": "Insufficient power to detect the MDE",
            "module": "power_calculator",
            "priority": 1,
        },
    ],
    "anomaly_critical": [
        {
            "action": "Check pipeline health",
            "reason": "Critical anomaly may be data issue",
            "module": "pipeline_health",
            "priority": 0,
        },
    ],
}


def adaptive_recommendations(
    result: Any = None,
    signals: Dict = None,
    session: Any = None,
    llm: Any = None,
) -> List[Dict]:
    sigs = signals or {}
    recs: List[Dict] = []

    # Rule-based recommendations
    if sigs.get("srm_detected"):
        recs.extend(_RECOMMENDATION_RULES["srm_detected"])
    elif sigs.get("simpsons_detected"):
        recs.extend(_RECOMMENDATION_RULES["simpsons_paradox_detected"])
    elif sigs.get("significant"):
        key = (
            "experiment_significant_ship" if sigs.get("ship") else "experiment_significant_no_ship"
        )
        recs.extend(_RECOMMENDATION_RULES[key])
    elif sigs.get("anomaly_severity") == "critical":
        recs.extend(_RECOMMENDATION_RULES["anomaly_critical"])
    elif not sigs.get("power_ok", True):
        recs.extend(_RECOMMENDATION_RULES["low_power"])
    else:
        recs.extend(_RECOMMENDATION_RULES["experiment_not_significant"])

    # Deduplicate
    seen = set()
    dedup = []
    for r in sorted(recs, key=lambda x: x.get("priority", 99)):
        key = r["module"]
        if key not in seen:
            seen.add(key)
            dedup.append(r)

    # LLM enrichment
    if llm is not None and result is not None:
        try:
            result_summary = (
                str(result)[:400] if not isinstance(result, dict) else str(result)[:400]
            )
            prompt = (
                f"Experiment result summary: {result_summary}\n"
                f"Signals: {sigs}\n"
                f"Existing recommendations: {[r['action'] for r in dedup[:3]]}\n\n"
                "Suggest ONE additional specific action (not already listed) that would "
                "generate the most analytical value. Format: action|reason|module_key"
            )
            resp = str(llm.ask(prompt)).strip()
            parts = resp.split("|")
            if len(parts) >= 2:
                dedup.append(
                    {
                        "action": parts[0].strip(),
                        "reason": parts[1].strip(),
                        "module": (
                            parts[2].strip().lower().replace(" ", "_")
                            if len(parts) > 2
                            else "experiment_analysis"
                        ),
                        "priority": 3,
                        "llm_suggested": True,
                    }
                )
        except Exception as e:
            logger.debug("Adaptive recommendations LLM failed: %s", e)

    return dedup[:6]


# ─────────────────────────────────────────────────────────────────────────────
# ROI GAP EXPLANATION
# ─────────────────────────────────────────────────────────────────────────────


def explain_roi_gap(
    experiment_lift_pp: float,
    production_lift_pp: float,
    experiment_name: str = "",
    concurrent_ships: List[Dict] = None,
    llm: Any = None,
) -> str:
    gap = production_lift_pp - experiment_lift_pp
    sign = "lower" if gap < 0 else "higher"
    conc = (
        ", ".join(s.get("name", str(s)) for s in (concurrent_ships or [])[:3]) or "none identified"
    )

    if llm is None:
        return (
            f"The post-ship lift ({production_lift_pp:+.2f}pp) is {abs(gap):.2f}pp {sign} than "
            f"the experiment measured ({experiment_lift_pp:+.2f}pp). "
            f"Likely causes: novelty/Hawthorne effect, concurrent feature confounds "
            f"({conc}), seasonal variation, or population drift."
        )

    prompt = f"""Senior data scientist explaining why post-ship ROI differs from experiment.

Experiment: {experiment_name}
Experiment lift: {experiment_lift_pp:+.2f}pp IOR
Post-ship lift:  {production_lift_pp:+.2f}pp IOR
Gap: {abs(gap):.2f}pp {sign} than experiment

Concurrent features shipped: {conc}

In 3-5 sentences: most likely reason(s) for the gap.
Cover: novelty/Hawthorne effects, concurrent confounds, seasonal variation, population drift, SRM-induced bias.
End with one concrete recommendation for the next measurement cycle.
No emojis."""
    try:
        return str(llm.ask(prompt))
    except Exception as e:
        return f"(Gap explanation unavailable: {e})"


# ─────────────────────────────────────────────────────────────────────────────
# OPEN QUESTION GENERATION
# ─────────────────────────────────────────────────────────────────────────────


def generate_open_questions(
    experiment_name: str,
    result: Dict,
    llm: Any = None,
) -> List[str]:
    # Static rules
    questions: List[str] = []
    if result.get("srm_detected"):
        questions.append(
            "What caused the sample ratio mismatch? Is the assignment logic deterministic?"
        )
    if result.get("simpsons_paradox_detected"):
        questions.append(
            "Which dimension is confounding the aggregate result, and should we stratify the rollout?"
        )
    if result.get("time_decay"):
        td = result["time_decay"]
        if td.get("decay_direction") == "weakening":
            questions.append(
                "Why is the treatment effect weakening over time? Novelty effect or feature degradation?"
            )
    if result.get("cohort_effect", {}).get("divergence"):
        questions.append(
            "New and returning users respond differently — should we personalise the rollout?"
        )
    if result.get("significant") and not result.get("ship"):
        questions.append(
            "The experiment is significant but not being shipped — what specific blocker needs resolving?"
        )

    if llm is not None:
        try:
            summary = str(result)[:500]
            prompt = (
                f"Experiment '{experiment_name}' results summary:\n{summary}\n\n"
                "Generate 2 specific follow-up analytical questions that would generate "
                "the most value for the team. Each question must be answerable with data. "
                "One question per line. No numbering."
            )
            resp = str(llm.ask(prompt))
            for line in resp.strip().split("\n"):
                line = line.strip().lstrip("•-1234567890. ")
                if len(line) > 20:
                    questions.append(line)
        except Exception as e:
            logger.debug("open question LLM failed: %s", e)

    return list(dict.fromkeys(questions))[:5]  # deduplicate, keep up to 5


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT CONTEXT BUILDER
# ─────────────────────────────────────────────────────────────────────────────


def build_experiment_context(
    exp_name: str,
    exp_info: Dict,
    overall_results: Dict,
    segment_results: Dict,
    interesting: List,
    decision: str,
    reasoning: str,
    extra_insights: Dict = None,
    past_learnings: List[Dict] = None,
) -> Dict:
    overall_summary = "; ".join(
        f"{t}: Δ={r.get('delta_pp',0):+.2f}pp "
        f"[CI {r.get('ci_lo_pp',0):+.2f}, {r.get('ci_hi_pp',0):+.2f}] "
        f"p={r.get('p_value',1):.4f} n={r.get('n_treatment',0):,} "
        f"{'(sig)' if r.get('sig') or r.get('is_significant') else '(n.s.)'}"
        for t, r in overall_results.items()
    )

    seg_parts = []
    for dim, rows in segment_results.items():
        for r in [x for x in rows if x.get("sig") or x.get("is_significant")][:4]:
            seg_parts.append(
                f"{r.get('dim',dim)}={r.get('level','?')}: Δ={r.get('delta_pp',0):+.2f}pp (sig)"
            )
    segment_summary = "; ".join(seg_parts) or "No significant segment-level effects."

    interesting_summary = (
        ", ".join(
            f"{kind}: {r.get('dim','?')}={r.get('level','?')} Δ={r.get('delta_pp',0):+.2f}pp"
            for kind, r in (interesting or [])[:5]
        )
        or "None detected."
    )

    time_trend = "Not computed."
    if extra_insights and extra_insights.get("time_decay"):
        td = extra_insights["time_decay"]
        time_trend = td.get("summary", "")

    ei_summary = ""
    if extra_insights:
        parts = []
        if extra_insights.get("cohort_effect"):
            parts.append(f"Cohort effect: {extra_insights['cohort_effect'].get('summary','')}")
        if extra_insights.get("cross_metric"):
            parts.append(f"Cross-metric: {extra_insights['cross_metric'].get('summary','')}")
        ei_summary = "; ".join(parts) or "(No additional insights)"

    # Format past learnings
    if past_learnings:
        pl_text = "\n".join(
            f"• [{l.get('id','')}] {l.get('experiment_name','')}: "
            f"{l.get('key_learning','')} | What worked: {l.get('what_worked','')}"
            for l in past_learnings[:3]
        )
    else:
        pl_text = "(No relevant prior experiments in learnings repository)"

    return {
        "experiment": exp_name,
        "description": exp_info.get("description", ""),
        "hypothesis": exp_info.get("hypothesis", "(not recorded)"),
        "method": exp_info.get("method", "A/B test"),
        "team": exp_info.get("team", ""),
        "decision": decision,
        "reasoning": reasoning,
        "overall_summary": overall_summary,
        "segment_summary": segment_summary,
        "interesting_summary": interesting_summary,
        "time_trend_summary": time_trend,
        "extra_insights": ei_summary,
        "past_learnings": pl_text,
        "n_past_learnings": len(past_learnings) if past_learnings else 0,
    }


__all__ = [
    "mine_additional_insights",
    "synthesise_findings",
    "generate_root_cause",
    "adaptive_recommendations",
    "explain_roi_gap",
    "generate_open_questions",
    "build_experiment_context",
]
