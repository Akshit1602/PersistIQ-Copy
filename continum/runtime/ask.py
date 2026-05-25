from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("continum.runtime.ask")


# ─────────────────────────────────────────────────────────────────────────────
# TURN — a single conversation exchange
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Turn:
    question:   str
    response:   str
    intent:     str
    entities:   Dict[str, Any] = field(default_factory=dict)
    timestamp:  str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ─────────────────────────────────────────────────────────────────────────────
# INTENT TAXONOMY
# ─────────────────────────────────────────────────────────────────────────────

class Intent:
    WHY_DROPPED      = "why_dropped"
    WHY_IMPROVED     = "why_improved"
    NEXT_STEP        = "next_step"
    SIGNIFICANCE     = "significance"
    SEGMENT_EXPLAIN  = "segment_explain"
    CAUSAL_EXPLAIN   = "causal_explain"
    SUMMARISE        = "summarise"
    HEALTH_CHECK     = "health_check"
    COMPARE          = "compare"
    ANOMALY          = "anomaly"
    LEARNINGS        = "learnings"
    METRICS          = "metrics"
    INVESTIGATE      = "investigate"    # recursive drill-down
    COHORT           = "cohort"
    ASSUMPTION       = "assumption"
    LONGITUDINAL     = "longitudinal"
    GENERAL          = "general"


_PATTERNS: List[Tuple[str, str]] = [
    (r"why.*(drop|declin|fall|decrease|worse|lower|regress)",   Intent.WHY_DROPPED),
    (r"why.*(improv|increas|lift|better|higher|win)",           Intent.WHY_IMPROVED),
    (r"(investig|drill|dig|explor|root cause|explain why)",     Intent.INVESTIGATE),
    (r"(what.*(next|should|do)|recommend|suggest)",             Intent.NEXT_STEP),
    (r"(significant|p.val|stat|result|verdict|ship)",           Intent.SIGNIFICANCE),
    (r"(segment|cohort|slice|mobile|enterprise|country).*(under|over|worse|better|differ|explain)", Intent.SEGMENT_EXPLAIN),
    (r"(causal|cause|drove|driven|impact|effect|attribut)",     Intent.CAUSAL_EXPLAIN),
    (r"(summar|explain|tell me|describe|overview|readout|brief)",Intent.SUMMARISE),
    (r"(health|srm|guardrail|anomal|monitor|ratio)",            Intent.HEALTH_CHECK),
    (r"(longitudinal|trend|over time|week.over.week|yoy|past exp)", Intent.LONGITUDINAL),
    (r"(compar|vs\.?|versus|difference|against|side.by.side)",  Intent.COMPARE),
    (r"(anomal|outlier|weird|unexpected|strange|spike|dip)",    Intent.ANOMALY),
    (r"(learn|histor|previous|before|we ran|last time)",        Intent.LEARNINGS),
    (r"(kpi|metric|measure|track|baseline)",                    Intent.METRICS),
    (r"(cohort|variant|group|arm|assignment|balance)",          Intent.COHORT),
    (r"(assum|alpha|power|sample size|threshold|guardrail)",    Intent.ASSUMPTION),
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
        from continum.core.semantic_layer.metric_registry import METRIC_REGISTRY
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
        from continum.core.semantic_layer.dimension_catalog import DIMENSION_CATALOG
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
# REASONING ENGINES
# ─────────────────────────────────────────────────────────────────────────────

def _safe_get(obj, *keys, default=None):
    for k in keys:
        try:
            v = getattr(obj, k, None)
            if v is not None:
                return v
        except Exception:
            pass
        if isinstance(obj, dict):
            v = obj.get(k)
            if v is not None:
                return v
    return default


def _get_result(session):
    if session is None:
        return None
    r = session.get("experiment_result") or session.get("experiment_analysis_result")
    if r and isinstance(r, dict):
        return r.get("result") or r
    return r


def reason_why_dropped(question: str, entities: Dict, session, bus, memory) -> str:
    result = _get_result(session)
    exp    = session.active_experiment if session else None
    lines  = [f"🔍 Root-Cause Investigation{': ' + exp if exp else ''}\n"]

    # Step 1 — SRM check
    srm = _safe_get(result, "srm_detected", default=False)
    srm_p = _safe_get(result, "srm_p_value")
    if srm:
        lines.append("  ❶ SRM DETECTED — assignment mechanism is broken.")
        lines.append(f"     p={srm_p:.4f}. This invalidates the result.")
        lines.append("     Action: pause experiment, audit randomisation logic.\n")
    else:
        srm_p_str = f"p={srm_p:.4f}" if srm_p is not None else "p=n/a"
        lines.append(f"  ❶ SRM clear ({srm_p_str}). Assignment OK.\n")

    # Step 2 — segment drivers
    slices = _safe_get(result, "slice_findings", default=[]) or []
    seg_filter = entities.get("segments", [])
    relevant_slices = []
    if seg_filter:
        for sf in seg_filter:
            dim, val = sf.get("dimension"), sf.get("value")
            relevant_slices = [
                s for s in slices
                if (dim is None or getattr(s, "dimension_name", "") == dim)
                and (val is None or getattr(s, "dimension_value", "").lower() == str(val).lower())
            ]
    if not relevant_slices:
        relevant_slices = sorted(slices, key=lambda s: abs(_safe_get(s.delta if hasattr(s,"delta") else s, "delta_pp") or 0), reverse=True)[:5]

    if relevant_slices:
        lines.append("  ❷ Segment drivers:")
        for s in relevant_slices[:4]:
            d     = getattr(s, "delta", None) or s
            dp    = float(_safe_get(d, "delta_pp") or 0)
            pv    = float(_safe_get(d, "p_value") or 1)
            sig   = "✅ sig" if _safe_get(d, "is_significant") else "— not sig"
            spx   = " ⚠️  Simpson's paradox" if getattr(s, "simpsons_paradox_flag", False) else ""
            dim   = getattr(s, "dimension_name", "")
            val   = getattr(s, "dimension_value", "")
            lines.append(f"     {dim}={val:<20}  Δ={dp:+.3f}pp  p={pv:.4f}  {sig}{spx}")
        lines.append("")
    else:
        lines.append("  ❷ No segment data loaded. Run experiment_analysis first.\n")

    # Step 3 — guardrail violations
    violations = _safe_get(result, "guardrail_violations", default=[]) or []
    if violations:
        lines.append("  ❸ Guardrail violations:")
        for v in violations[:3]:
            name = _safe_get(v, "guardrail_name", default="unknown")
            mag  = float(_safe_get(v, "violation_magnitude") or 0)
            lines.append(f"     ⚠️  {name}  magnitude={mag:+.4f}")
        lines.append("")
    else:
        lines.append("  ❸ No guardrail violations.\n")

    # Step 4 — causal estimates
    causal = session.get("causal_analysis_result") if session else None
    if causal:
        estimates = _safe_get(causal, "estimates", default=[]) or []
        if estimates:
            lines.append("  ❹ Causal estimates:")
            for e in estimates[:2]:
                method = _safe_get(e, "method", default="?")
                est    = float(_safe_get(e, "estimate") or 0)
                pv     = float(_safe_get(e, "p_value") or 1)
                lines.append(f"     [{method}] estimate={est:+.4f}  p={pv:.4f}")
            lines.append("")
    else:
        lines.append("  ❹ No causal analysis run yet. Try: causal_analysis.\n")

    # Step 5 — historical comparison
    if memory:
        hist_exp = exp or "conversion"
        similar = memory.search_similar(hist_exp, limit=2)
        if similar:
            lines.append("  ❺ Similar past experiments:")
            for r in similar:
                dp  = float(r.get("delta_pp") or 0)
                sig = "✅" if r.get("is_significant") else "—"
                lines.append(f"     {sig} {r.get('experiment_name',''):<38}  Δ={dp:+.3f}pp")
            lines.append("")
        else:
            lines.append("  ❺ No similar experiments in memory yet.\n")

    # Synthesis
    primary = _safe_get(result, "primary_delta")
    dp = float(_safe_get(primary, "delta_pp") or 0)
    lines.append("  ── Synthesis ─────────────────────────────────────────────")
    if srm:
        lines.append("  The drop is UNRELIABLE — SRM detected. Fix assignment first.")
    elif violations:
        lines.append("  A regression in a guardrail metric likely explains the drop.")
        lines.append("  Do not ship without resolving guardrail violations.")
    elif relevant_slices and any(getattr(s, "simpsons_paradox_flag", False) for s in relevant_slices):
        lines.append("  Simpson's paradox: a composition shift (not a real effect)")
        lines.append("  is masking the true treatment effect. Segment separately.")
    elif relevant_slices:
        top = relevant_slices[0]
        d   = getattr(top, "delta", None) or top
        dv  = getattr(top, "dimension_value", "")
        lines.append(f"  The drop is driven primarily by the '{dv}' segment.")
        lines.append("  Investigate whether this segment is disproportionately exposed.")
    elif dp < -0.01:
        lines.append("  The drop appears real and consistent. Recommend: do not ship.")
    else:
        lines.append("  Drop is small in magnitude. May be noise — check power.")

    return "\n".join(lines)


def reason_significance(session, bus) -> str:
    result = _get_result(session)
    if result is None:
        return (
            "No experiment result loaded.\n"
            "Run experiment_analysis first, then ask again."
        )
    primary = _safe_get(result, "primary_delta")
    dp      = float(_safe_get(primary, "delta_pp") or 0)
    pv      = float(_safe_get(primary, "p_value") or 1)
    is_sig  = bool(_safe_get(primary, "is_significant") or False)
    verdict = str(_safe_get(result, "verdict") or "—")
    ship    = str(_safe_get(result, "ship_recommendation") or "—")
    srm     = bool(_safe_get(result, "srm_detected") or False)
    srm_p   = _safe_get(result, "srm_p_value")
    n_ctrl  = int(_safe_get(primary, "n_control") or 0)
    n_treat = int(_safe_get(primary, "n_treatment") or 0)
    ci_lo   = float(_safe_get(primary, "ci_lo") or 0)
    ci_hi   = float(_safe_get(primary, "ci_hi") or 0)

    sig_str   = "✅ Statistically significant" if is_sig else "❌ NOT statistically significant"
    ship_icon = "✅" if "ship" in ship.lower() and "not" not in ship.lower() else "⛔"
    srm_line  = (f"\n  ⚠️  SRM DETECTED (p={srm_p:.4f}) — treat with caution"
                 if srm else f"\n  ✅ No SRM (p={srm_p:.4f})" if srm_p else "")

    lines = [
        f"📊 {sig_str}",
        f"",
        f"  Δ = {dp:+.4f}pp  |  p = {pv:.4f}  |  95% CI [{ci_lo:+.4f}, {ci_hi:+.4f}]",
        f"  n = {n_ctrl:,} control / {n_treat:,} treatment",
        f"  Verdict: {verdict.upper()}",
        f"  {ship_icon} Recommendation: {ship.replace('_', ' ').upper()}",
        srm_line,
    ]

    # Bayesian enrichment from bus
    bay_ins = [i for i in (bus.all() if bus else []) if "bayesian" in i.message.lower()]
    if bay_ins:
        lines.append(f"\n  📊 Bayesian: {bay_ins[-1].message}")

    return "\n".join(lines)


def reason_next_step(session, bus, memory) -> str:
    lines = ["💡 Recommended next steps based on your session:\n"]

    # From bus next-steps
    ns = bus.by_type("next_step") if bus else []
    if ns:
        for i in ns[-5:]:
            lines.append(f"  ▶  {i.message}")
            if i.detail:
                lines.append(f"     {i.detail}")

    # From session recommendations
    if session and session.recommendations:
        lines.append("\n  Workflow chain:")
        for r in session.recommendations[:3]:
            lines.append(f"  [{r.priority}] {r.action}  — {r.reason}")

    # Context-aware suggestions
    if session:
        history_modules = {r.module for r in session.execution_history}
        result = _get_result(session)
        srm = _safe_get(result, "srm_detected", default=False) if result else False

        if srm:
            lines.append("\n  ⚠️  Priority: SRM detected — investigate assignment before any analysis.")
        elif "experiment_analysis" in history_modules and "causal_analysis" not in history_modules:
            lines.append("\n  📌 Run causal_analysis to validate A/B findings with causal methods.")
        elif "causal_analysis" in history_modules and "learnings_repository" not in history_modules:
            lines.append("\n  📌 Store findings: run learnings_repository.")
        elif not history_modules:
            lines.append("\n  📌 Start with schema_discovery to understand your data.")

    if len(lines) == 1:
        lines.append("  Run any module to generate recommendations.")

    return "\n".join(lines)


def reason_longitudinal(question: str, session, memory) -> str:
    lines = ["📈 Longitudinal Analysis:\n"]
    exp = session.active_experiment if session else None

    if memory:
        # Get all experiments with their deltas
        try:
            db_temp = memory._connect()
            rows = db_temp.execute("""
                SELECT experiment_name, recorded_at, delta_pp, p_value,
                       is_significant, primary_metric
                FROM experiment_memory
                ORDER BY recorded_at DESC
                LIMIT 20
            """).fetchall()
            if not memory._in_memory:
                db_temp.close()

            if rows:
                lines.append("  Experiment history (most recent first):\n")
                lines.append(f"  {'Experiment':<38}  {'Δ (pp)':>8}  {'p-val':>7}  Sig")
                lines.append(f"  {'─' * 62}")
                for r in rows[:10]:
                    name, ts, dp, pv, sig, metric = r
                    dp   = float(dp or 0)
                    pv   = float(pv or 1)
                    s    = "✅" if sig else "—"
                    lines.append(f"  {str(name):<38}  {dp:>+8.4f}  {pv:>7.4f}  {s}")

                # Compute trend
                dps = [float(r[2] or 0) for r in rows if r[2] is not None]
                if len(dps) >= 3:
                    avg = sum(dps) / len(dps)
                    recent_avg = sum(dps[:3]) / 3
                    trend = "improving" if recent_avg > avg else "declining" if recent_avg < avg else "stable"
                    lines.append(f"\n  Trend: {trend}  "
                                 f"(recent avg Δ={recent_avg:+.3f}pp  vs all-time {avg:+.3f}pp)")
            else:
                lines.append("  No historical experiments in memory yet.")
        except Exception as e:
            lines.append(f"  Memory query error: {e}")
    else:
        lines.append("  Memory not available.")

    return "\n".join(lines)


def reason_causal_explain(question: str, entities: Dict, session, bus) -> str:
    result = _get_result(session)
    lines  = ["🔗 Causal Chain Analysis:\n"]

    primary = _safe_get(result, "primary_delta")
    dp = float(_safe_get(primary, "delta_pp") or 0)

    lines.append("  Direct effect:")
    if dp > 0.01:
        lines.append(f"  → Treatment caused a {dp:+.3f}pp lift in the primary metric.")
    elif dp < -0.01:
        lines.append(f"  → Treatment caused a {dp:+.3f}pp regression.")
    else:
        lines.append(f"  → Minimal direct effect detected (Δ={dp:+.4f}pp).")

    # Mediation analysis from session
    causal_result = session.get("causal_analysis_result") if session else None
    estimates = []
    if causal_result:
        estimates = _safe_get(causal_result, "estimates", default=[]) or []
        if estimates:
            lines.append("\n  Causal method estimates:")
            for e in estimates:
                m   = _safe_get(e, "method", default="?")
                est = float(_safe_get(e, "estimate") or 0)
                pv  = float(_safe_get(e, "p_value") or 1)
                sig = "✅" if _safe_get(e, "is_significant") else "—"
                lines.append(f"    {sig} [{m:<24}]  estimate={est:+.4f}  p={pv:.4f}")

    # Confounders / moderators from segments
    slices = _safe_get(result, "slice_findings", default=[]) or []
    heterogeneous = [s for s in slices if getattr(s, "is_heterogeneous", False)]
    if heterogeneous:
        lines.append("\n  Significant moderators (effect varies by):")
        for s in heterogeneous[:4]:
            d  = getattr(s, "delta", None) or s
            dp = float(_safe_get(d, "delta_pp") or 0)
            lines.append(f"    → {s.dimension_name}={s.dimension_value}  Δ={dp:+.3f}pp")

    if not estimates and not heterogeneous:
        lines.append("\n  Run causal_analysis to get DiD/PSM/ITS estimates.")

    return "\n".join(lines)


def reason_cohort(session, db) -> str:
    lines = ["👥 Cohort Inspection:\n"]
    try:
        from continum.runtime.inspect import inspect
        report = inspect("cohorts", session=session, db=db)
        if "error" in report or "status" in report:
            return f"  {report.get('error') or report.get('status')}"
        lines.append(f"  Experiment: {report.get('experiment')}")
        lines.append(f"  Total users: {report.get('total_users', 0):,}")
        srm = report.get("srm_detected", False)
        srm_p = report.get("srm_p_value")
        lines.append(f"  SRM: {'⚠️  DETECTED p=' + f'{srm_p:.4f}' if srm else '✅ Clean'}\n")
        for c in report.get("cohorts", []):
            bal = "✅" if c.get("balanced") else "⚠️ "
            lines.append(f"  {bal}  {c['variant']:<24}  {c['n_users']:>8,} users  ({c['pct']:.1f}%)")
    except Exception as e:
        lines.append(f"  Cohort inspection error: {e}")
    return "\n".join(lines)


def reason_assumption(session) -> str:
    lines = ["⚙️  Active Assumptions:\n"]
    try:
        from continum.runtime.inspect import inspect
        report = inspect("assumptions", session=session)
        stat = report.get("statistical", {})
        lines.append("  Statistical:")
        for k, v in stat.items():
            if v is not None:
                lines.append(f"    {k:<28}  {v}")
        design = report.get("design", {})
        lines.append("\n  Design:")
        for k, v in design.items():
            lines.append(f"    {k:<28}  {v}")
    except Exception as e:
        lines.append(f"  Assumption inspection error: {e}")
    return "\n".join(lines)


def reason_summarise(session, bus, memory) -> str:
    lines = ["📝 Session Summary:\n"]
    if session:
        lines.append(f"  {session.summary_line()}")
        if session.active_experiment:
            lines.append(f"\n  Active experiment: {session.active_experiment}")
        if session.active_metrics:
            lines.append(f"  Active metrics: {', '.join(session.active_metrics[:5])}")
        if session.execution_history:
            lines.append(f"\n  Modules run:")
            for rec in session.execution_history[-6:]:
                icon = "✅" if rec.ok else "❌"
                lines.append(f"    {icon} {rec.module:<30}  {rec.elapsed_s:.2f}s  {rec.summary[:50]}")
    if bus:
        w = len(bus.warnings())
        r = len(bus.recommendations())
        lines.append(f"\n  Intelligence: {w} warning{'s' if w != 1 else ''}  ·  {r} recommendation{'s' if r != 1 else ''}")
        for ins in bus.all()[-4:]:
            lines.append(f"    {ins.one_liner()}")
    if memory:
        n = memory.experiment_count()
        if n:
            lines.append(f"\n  Memory: {n} experiments stored")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# REASONING CHAIN
# The difference between routing and reasoning.
# ─────────────────────────────────────────────────────────────────────────────

from dataclasses import dataclass as _dc, field as _field


@_dc
class Evidence:
    source:     str
    claim:      str
    confidence: float          # 0.0 – 1.0
    valence:    str            # "supports" | "contradicts" | "uncertain"
    data:       Dict = _field(default_factory=dict)


class ReasoningChain:

    def __init__(self):
        self.evidence: List[Evidence] = []
        self.hypothesis: str = ""

    def set_hypothesis(self, h: str) -> "ReasoningChain":
        self.hypothesis = h
        return self

    def add(self, source: str, claim: str, confidence: float,
            valence: str = "supports", **data) -> "ReasoningChain":
        self.evidence.append(Evidence(
            source=source, claim=claim,
            confidence=min(1.0, max(0.0, confidence)),
            valence=valence, data=data,
        ))
        return self

    def build_from_context(self, session, bus, memory) -> "ReasoningChain":
        result = _get_result(session)

        # ① Assignment integrity
        if result:
            srm = bool(_safe_get(result, "srm_detected") or False)
            srm_p = float(_safe_get(result, "srm_p_value") or 1.0)
            if srm:
                self.add("SRM detector", f"Sample ratio mismatch (p={srm_p:.4f})",
                         confidence=0.95, valence="contradicts",
                         srm_p=srm_p)
            else:
                self.add("SRM detector", "Assignment is balanced — no SRM detected",
                         confidence=0.85, valence="supports")

        # ② Primary metric
        if result:
            primary = _safe_get(result, "primary_delta")
            dp  = float(_safe_get(primary, "delta_pp") or 0)
            pv  = float(_safe_get(primary, "p_value") or 1)
            sig = bool(_safe_get(primary, "is_significant") or False)
            conf = max(0.0, 1.0 - pv) if sig else min(0.5, 1.0 - pv)
            val  = "supports" if (sig and dp > 0) else \
                   "contradicts" if (sig and dp < 0) else "uncertain"
            self.add("A/B analysis",
                     f"Δ={dp:+.3f}pp (p={pv:.4f}){' ✅ significant' if sig else ' — not significant'}",
                     confidence=conf, valence=val, delta_pp=dp, p_value=pv)

        # ③ Guardrail violations
        if result:
            violations = _safe_get(result, "guardrail_violations", default=[]) or []
            for v in violations[:2]:
                name = _safe_get(v, "guardrail_name", default="guardrail")
                mag  = float(_safe_get(v, "violation_magnitude") or 0)
                self.add("Guardrail monitor",
                         f"{name} violated (magnitude={mag:+.4f})",
                         confidence=0.9, valence="contradicts")

        # ④ Causal estimates
        causal = session.get("causal_analysis_result") if session else None
        if causal:
            estimates = _safe_get(causal, "estimates", default=[]) or []
            for e in estimates[:3]:
                method = _safe_get(e, "method", default="?")
                est    = float(_safe_get(e, "estimate") or 0)
                pv_c   = float(_safe_get(e, "p_value") or 1)
                sig_c  = bool(_safe_get(e, "is_significant") or False)
                conf   = 0.85 if sig_c else 0.4
                val    = "supports" if (sig_c and est > 0) else \
                         "contradicts" if (sig_c and est < 0) else "uncertain"
                self.add(f"Causal [{method}]",
                         f"estimate={est:+.4f} (p={pv_c:.4f})",
                         confidence=conf, valence=val)

        # ⑤ Historical patterns
        if memory:
            exp = session.active_experiment if session else None
            similar = memory.search_similar(exp or "", limit=3) if exp else []
            if similar:
                sig_count = sum(1 for r in similar if r.get("is_significant"))
                avg_dp    = sum(float(r.get("delta_pp") or 0) for r in similar) / len(similar)
                self.add("Cross-experiment memory",
                         f"{sig_count}/{len(similar)} similar experiments were significant, avg Δ={avg_dp:+.3f}pp",
                         confidence=0.6, valence="supports" if avg_dp > 0 else "uncertain",
                         n_similar=len(similar))

        # ⑥ Intelligence bus warnings
        if bus:
            for w in bus.warnings()[-2:]:
                self.add("Intelligence bus",
                         w.message,
                         confidence=0.8, valence="contradicts")

        return self

    def synthesise(self) -> str:
        if not self.evidence:
            return "Insufficient evidence to reason from. Run analysis modules first."

        supporting   = [e for e in self.evidence if e.valence == "supports"]
        contradicting= [e for e in self.evidence if e.valence == "contradicts"]
        uncertain    = [e for e in self.evidence if e.valence == "uncertain"]

        # Weighted confidence
        total_conf = sum(e.confidence for e in self.evidence)
        support_conf = sum(e.confidence for e in supporting)
        weight = support_conf / total_conf if total_conf > 0 else 0.5

        if contradicting and any(e.source == "SRM detector" for e in contradicting):
            verdict = "⛔ Results are NOT trustworthy due to sample ratio mismatch."
        elif contradicting and weight < 0.4:
            verdict = "⛔ Evidence weighs against a positive outcome."
        elif supporting and weight > 0.6:
            verdict = "✅ Evidence broadly supports a positive outcome."
        else:
            verdict = "⚠️  Evidence is mixed — proceed with caution."

        return verdict

    def render(self) -> str:
        if not self.evidence:
            return "No evidence gathered."

        lines = []
        if self.hypothesis:
            lines.append(f"Hypothesis: {self.hypothesis}\n")

        lines.append("Evidence gathered:\n")
        for i, e in enumerate(self.evidence, 1):
            icon = "✅" if e.valence == "supports" else \
                   "❌" if e.valence == "contradicts" else "?"
            bar  = "█" * int(e.confidence * 8) + "░" * (8 - int(e.confidence * 8))
            lines.append(
                f"  {i}. {icon} [{e.source}]\n"
                f"     {e.claim}\n"
                f"     Confidence: {bar} {e.confidence:.0%}\n"
            )

        lines.append(f"Synthesis: {self.synthesise()}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "hypothesis": self.hypothesis,
            "evidence": [
                {"source": e.source, "claim": e.claim,
                 "confidence": e.confidence, "valence": e.valence}
                for e in self.evidence
            ],
            "synthesis": self.synthesise(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-TURN COPILOT
# ─────────────────────────────────────────────────────────────────────────────

class ContinumCopilot:

    def __init__(self, session=None, bus=None, memory=None, db=None):
        self.session  = session
        self.bus      = bus
        self.memory   = memory
        self.db       = db
        self.history: List[Turn] = []
        self._last_chain: Optional[ReasoningChain] = None

    def ask(self, question: str) -> str:
        if not question.strip():
            return "Please ask a question."

        intent   = detect_intent(question)
        entities = extract_entities(question)

        # Cross-turn entity resolution: carry forward segments if user says "it" / "that"
        if not entities.get("segments") and self.history:
            prev_segs = self.history[-1].entities.get("segments", [])
            if prev_segs and re.search(r"\bit\b|that|the segment|same", question.lower()):
                entities["segments"] = prev_segs

        response = self._route(question, intent, entities)

        self.history.append(Turn(
            question=question, response=response,
            intent=intent, entities=entities,
        ))
        return response

    def ask_with_chain(self, question: str) -> Dict:
        intent   = detect_intent(question)
        entities = extract_entities(question)

        chain = None
        if intent in (Intent.WHY_DROPPED, Intent.INVESTIGATE, Intent.SIGNIFICANCE,
                      Intent.CAUSAL_EXPLAIN, Intent.SEGMENT_EXPLAIN, Intent.WHY_IMPROVED):
            chain = ReasoningChain()
            chain.set_hypothesis(self._hypothesis_for(intent, entities))
            chain.build_from_context(self.session, self.bus, self.memory)
            self._last_chain = chain

        response = self._route(question, intent, entities)
        self.history.append(Turn(
            question=question, response=response,
            intent=intent, entities=entities,
        ))
        return {
            "response": response,
            "chain":    chain.to_dict() if chain else None,
            "intent":   intent,
            "entities": entities,
        }

    def _hypothesis_for(self, intent: str, entities: Dict) -> str:
        exp = self.session.active_experiment if self.session else "this experiment"
        if intent == Intent.WHY_DROPPED:
            seg = entities.get("segments", [{}])[0].get("value", "") if entities.get("segments") else ""
            return f"The treatment caused a metric drop{' in ' + seg if seg else ''} in '{exp}'."
        if intent == Intent.WHY_IMPROVED:
            return f"The treatment caused a genuine improvement in '{exp}'."
        if intent == Intent.SIGNIFICANCE:
            return f"'{exp}' has a statistically significant effect."
        if intent == Intent.CAUSAL_EXPLAIN:
            return f"The observed effect in '{exp}' is causally driven by the treatment."
        return f"'{exp}' produced a meaningful result."

    def _route(self, question: str, intent: str, entities: Dict) -> str:
        s, b, m, db = self.session, self.bus, self.memory, self.db

        if intent in (Intent.WHY_DROPPED, Intent.INVESTIGATE, Intent.SEGMENT_EXPLAIN):
            base = reason_why_dropped(question, entities, s, b, m)
            # Enrich with historical prior
            prior_text = self._get_prior_text()
            return base + ("\n\n" + prior_text if prior_text else "")

        elif intent == Intent.WHY_IMPROVED:
            return reason_why_dropped(question, entities, s, b, m)

        elif intent == Intent.SIGNIFICANCE:
            base  = reason_significance(s, b)
            chain = ReasoningChain()
            chain.set_hypothesis(self._hypothesis_for(intent, entities))
            chain.build_from_context(s, b, m)
            synthesis = chain.synthesise()
            return f"{base}\n\n  {synthesis}"

        elif intent == Intent.NEXT_STEP:
            return reason_next_step(s, b, m)

        elif intent == Intent.CAUSAL_EXPLAIN:
            return reason_causal_explain(question, entities, s, b)

        elif intent == Intent.SUMMARISE:
            return reason_summarise(s, b, m)

        elif intent == Intent.HEALTH_CHECK:
            return self._respond_health(s, b)

        elif intent in (Intent.COMPARE, Intent.LEARNINGS):
            return self._respond_learnings(question, m)

        elif intent == Intent.LONGITUDINAL:
            base  = reason_longitudinal(question, s, m)
            # Add org patterns
            try:
                from continum.runtime.patterns import get_miner
                summary = get_miner(m).mine_all().get("summary", "")
                if summary:
                    return base + "\n\n📊 Organizational patterns:\n" + "\n".join(
                        f"  {ln}" for ln in summary.split("\n"))
            except Exception:
                pass
            return base

        elif intent == Intent.COHORT:
            return reason_cohort(s, db)

        elif intent == Intent.ASSUMPTION:
            return reason_assumption(s)

        elif intent == Intent.ANOMALY:
            return self._respond_health(s, b)

        else:
            return self._respond_general(question, b)

    def _get_prior_text(self) -> str:
        if not self.memory or not self.session:
            return ""
        exp = self.session.active_experiment
        if not exp:
            return ""
        try:
            from continum.runtime.patterns import get_miner
            prior = get_miner(self.memory).get_prior(exp)
            if prior.similar_experiments:
                return prior.narrative()
        except Exception:
            pass
        return ""

    def _respond_health(self, session, bus) -> str:
        warnings = bus.warnings() if bus else []
        lines = ["🩺 Health Check:\n"]
        if warnings:
            for i in warnings:
                lines.append(f"  {i.full_text()}\n")
        else:
            lines.append("  ✅ No active warnings.")
        return "\n".join(lines)

    def _respond_learnings(self, question: str, memory) -> str:
        lines = ["🧠 Experiment Learnings:\n"]
        kw = " ".join(w for w in question.split() if len(w) > 3)
        results = memory.search_similar(kw, limit=4) if memory else []
        if results:
            for r in results:
                sig = "✅" if r.get("is_significant") else "—"
                dp  = float(r.get("delta_pp") or 0)
                lines.append(f"  {sig}  {r['experiment_name']:<42}  Δ={dp:+.3f}pp")
                if r.get("narrative"):
                    lines.append(f"      {r['narrative'][:100]}…")
        else:
            lines.append("  No matching experiments in memory. Run analyses to populate.")
        return "\n".join(lines)

    def _respond_general(self, question: str, bus) -> str:
        insights = bus.all()[-6:] if bus else []
        # Try to generate a meaningful response even for open-ended questions
        if self.session and self.session.active_experiment:
            result = _get_result(self.session)
            if result:
                chain = ReasoningChain()
                chain.set_hypothesis("The current experiment result is interpretable.")
                chain.build_from_context(self.session, bus, self.memory)
                return (
                    f"Based on what I know about '{self.session.active_experiment}':\n\n"
                    f"{chain.render()}"
                )
        if not insights:
            return (
                "I'm ready to reason about your experiments.\n\n"
                "Try:\n"
                "  • 'Is this experiment significant?'\n"
                "  • 'Why did conversion drop in mobile?'\n"
                "  • 'Investigate the treatment'\n"
                "  • 'What should I run next?'\n"
                "  • 'Compare to past experiments'"
            )
        lines = ["Here's what I know from this session:\n"]
        for ins in insights:
            lines.append(f"  {ins.one_liner()}")
        return "\n".join(lines)

    def interactive(self) -> None:
        W = 72
        print(f"\n{'═' * W}")
        print(f"  🔬 ASK CONTINUM — Experimentation Reasoning")
        print(f"{'═' * W}")
        print("  Multi-turn reasoning. Type 'chain' to see evidence, 'exit' to leave.\n")

        while True:
            try:
                q = input("  Ask › ").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if q.lower() in ("exit", "quit", "q", "back"):
                break
            if q.lower() == "chain" and self._last_chain:
                print(f"\n{self._last_chain.render()}\n")
                continue
            if not q:
                continue
            print()
            result = self.ask_with_chain(q)
            for line in result["response"].split("\n"):
                print(f"  {line}")
            if result.get("chain"):
                print(f"\n  {'-' * 40}")
                print(f"  Type 'chain' to see the reasoning evidence.\n")
            else:
                print()


__all__ = [
    "ContinumCopilot",
    "detect_intent",
    "extract_entities",
    "Intent",
    "Turn",
    "ReasoningChain",
    "Evidence",
]
