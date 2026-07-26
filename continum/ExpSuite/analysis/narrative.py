from __future__ import annotations

import logging
import os
from collections import OrderedDict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("continum.intelligence.narrative")


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTIVE NARRATIVE
# ─────────────────────────────────────────────────────────────────────────────


def generate_executive_narrative(
    result,
    causal_estimates: List[Any] = None,
    bayesian: Optional[Dict] = None,
    llm=None,
) -> str:
    causal_estimates = causal_estimates or []

    if llm is not None:
        context = _build_narrative_context(result, causal_estimates, bayesian)
        prompt = (
            "You are a senior experimentation analyst writing an executive readout "
            "for a product and leadership team.\n\n"
            "Write a 5-7 sentence narrative covering:\n"
            "1. The experiment and what it tested\n"
            "2. The primary metric result (be specific with numbers)\n"
            "3. Whether the result is trustworthy (SRM, power)\n"
            "4. The most important segment finding (if any)\n"
            "5. What the causal estimates say (if available)\n"
            "6. The final recommendation and why\n\n"
            "Use plain business English. Be direct. No hedging. No bullets. "
            "No markdown. Specific numbers only.\n\n"
            f"DATA:\n{context}"
        )
        try:
            return str(llm.ask(prompt))
        except Exception as e:
            logger.warning("LLM narrative failed (%s) — using template", e)

    return _template_narrative(result, causal_estimates, bayesian)


def _build_narrative_context(result, causal_estimates, bayesian) -> str:
    d = result.primary_delta
    lines = [
        f"Experiment: {result.experiment_name}",
        f"Primary metric: {d.metric_display_name}",
        f"Control: {d.rate_control:.4%} ({d.n_control:,} obs)",
        f"Treatment: {d.rate_treatment:.4%} ({d.n_treatment:,} obs)",
        f"Δ = {d.delta_pp:+.4f}pp ({d.delta_rel:+.1%} relative)",
        f"95% CI: [{d.ci_lo:.4%}, {d.ci_hi:.4%}]",
        f"p-value: {d.p_value:.6f}",
        f"Significant at α=0.05: {d.is_significant}",
        f"SRM detected: {result.srm_detected} (p={result.srm_p_value:.4f})",
        f"Verdict: {result.verdict.value}",
        f"Recommendation: {result.ship_recommendation.value}",
        f"Blockers: {result.ship_blockers or 'None'}",
    ]
    if result.slice_findings:
        top = sorted(result.slice_findings, key=lambda s: abs(s.delta.delta_pp), reverse=True)[:3]
        for s in top:
            pf = " ⚠️ Simpson's paradox" if s.simpsons_paradox_flag else ""
            lines.append(
                f"Segment {s.dimension_name}={s.dimension_value}: "
                f"Δ={s.delta.delta_pp:+.4f}pp p={s.delta.p_value:.4f}{pf}"
            )
    if causal_estimates:
        for e in causal_estimates[:2]:
            lines.append(
                f"Causal ({e.method}): estimate={e.estimate:+.6f} "
                f"CI=[{e.ci_lo:+.4f},{e.ci_hi:+.4f}] p={e.p_value:.4f}"
            )
    if bayesian:
        lines.append(
            f"Bayesian P(T>C)={bayesian.get('prob_treat_better', 0):.4f} "
            f"decision={bayesian.get('decision', 'n/a')}"
        )
    return "\n".join(lines)


def _template_narrative(result, causal_estimates, bayesian) -> str:
    d = result.primary_delta
    sig = "statistically significant" if d.is_significant else "not statistically significant"
    delta = f"{d.delta_pp:+.2f}pp ({d.delta_rel:+.1%} relative)"
    ship = result.ship_recommendation.value.replace("_", " ").upper()
    ci = f"[{d.ci_lo*100:+.3f}pp, {d.ci_hi*100:+.3f}pp]"

    sentences = [
        f"Experiment '{result.experiment_name}' tested changes on {d.metric_display_name}.",
        f"The primary metric moved {delta} and was {sig} (p={d.p_value:.4f}, 95% CI {ci}).",
    ]
    if result.srm_detected:
        sentences.append(
            f"⚠️ Sample Ratio Mismatch was detected (p={result.srm_p_value:.4f}) — "
            "results should be interpreted with caution."
        )
    if result.slice_findings:
        top_slice = max(result.slice_findings, key=lambda s: abs(s.delta.delta_pp))
        sentences.append(
            f"The most notable segment effect was in "
            f"{top_slice.dimension_name}={top_slice.dimension_value} "
            f"(Δ={top_slice.delta.delta_pp:+.3f}pp, p={top_slice.delta.p_value:.4f})."
        )
        simpsons = [s for s in result.slice_findings if s.simpsons_paradox_flag]
        if simpsons:
            sentences.append(
                f"Simpson's Paradox was detected in "
                f"{simpsons[0].dimension_name}={simpsons[0].dimension_value} — "
                "the segment-level effect contradicts the overall direction."
            )
    if causal_estimates:
        e = causal_estimates[0]
        sentences.append(
            f"A {e.method} causal estimate corroborates this: "
            f"estimate={e.estimate:+.4f} (p={e.p_value:.4f})."
        )
    if bayesian:
        p_tb = bayesian.get("prob_treat_better", 0)
        sentences.append(
            f"Bayesian analysis gives P(treatment > control) = {p_tb:.1%}, "
            f"decision: {bayesian.get('decision', 'n/a')}."
        )
    if result.ship_blockers:
        sentences.append(f"Blockers preventing ship: {'; '.join(result.ship_blockers)}.")
    sentences.append(f"Recommendation: {ship}.")
    return " ".join(sentences)


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL NARRATIVE
# ─────────────────────────────────────────────────────────────────────────────


def generate_causal_narrative(
    estimate,
    primary_delta=None,
    llm=None,
) -> str:
    method = getattr(estimate, "method", "unknown")
    est = getattr(estimate, "estimate", 0)
    p = getattr(estimate, "p_value", 1.0)
    ci_lo = getattr(estimate, "ci_lo", est)
    ci_hi = getattr(estimate, "ci_hi", est)
    sig = p < 0.05

    if llm is not None:
        ctx = (
            f"Method: {method}\n"
            f"Causal estimate: {est:+.6f}\n"
            f"p-value: {p:.4f} ({'significant' if sig else 'not significant'})\n"
            f"95% CI: [{ci_lo:+.4f}, {ci_hi:+.4f}]\n"
        )
        if primary_delta:
            ctx += f"A/B estimate for comparison: {primary_delta.delta_pp:+.4f}pp\n"

        prompt = (
            "You are an experimentation analyst. In 2-3 sentences, interpret this "
            "causal estimate in plain business language:\n\n"
            f"{ctx}\n"
            "Cover: (1) what the estimate means in plain English, "
            "(2) whether it corroborates or contradicts the A/B result, "
            "(3) how much confidence the team should have. "
            "Be specific. Use numbers."
        )
        try:
            return str(llm.ask(prompt))
        except Exception as e:
            logger.warning("Causal narrative LLM failed: %s", e)

    method_labels = {
        "did_twfe": "Difference-in-Differences",
        "rdd_local_poly": "Regression Discontinuity",
        "arima_counterfactual": "ARIMA counterfactual",
        "bsts_local_level": "Bayesian Structural Time Series",
        "psm": "Propensity Score Matching",
        "synthetic_control": "Synthetic Control",
        "sarima_counterfactual": "Seasonal ARIMA counterfactual",
    }
    label = method_labels.get(method, method)
    sign = "increase" if est > 0 else "decrease"
    sig_t = "statistically significant" if sig else "not statistically significant"

    template = (
        f"The {label} analysis estimated a {sign} of {abs(est):.4f} "
        f"(p={p:.4f}, 95% CI [{ci_lo:+.4f}, {ci_hi:+.4f}]), "
        f"which is {sig_t}. "
    )
    if primary_delta and abs(primary_delta.delta_pp) > 0:
        direction_match = (est > 0) == (primary_delta.delta_pp > 0)
        corr = "corroborates" if direction_match else "contradicts"
        template += f"This {corr} the A/B estimate of {primary_delta.delta_pp:+.4f}pp. "
    template += (
        "Triangulating across both methods increases confidence in the direction " "of the effect."
        if sig
        else "The wide confidence interval suggests the data are insufficient to draw "
        "a strong causal conclusion."
    )
    return template


# ─────────────────────────────────────────────────────────────────────────────
# NEXT RECOMMENDATIONS
# ─────────────────────────────────────────────────────────────────────────────


def generate_next_recommendations(
    result,
    causal_estimates: List[Any] = None,
    llm=None,
) -> str:
    causal_estimates = causal_estimates or []

    if llm is not None:
        context = _build_narrative_context(result, causal_estimates, None)
        prompt = (
            "You are an experimentation strategist. Based on this experiment result, "
            "write 3-5 concrete, numbered next steps for the team. "
            "Be specific — mention metric names, segment names, and action owners. "
            "Cover: immediate actions, follow-up experiments, open risks.\n\n"
            f"DATA:\n{context}"
        )
        try:
            return str(llm.ask(prompt))
        except Exception as e:
            logger.warning("Next recommendations LLM failed: %s", e)

    # Deterministic recommendations
    rec = []
    d = result.primary_delta
    ship = result.ship_recommendation.value

    if result.srm_detected:
        rec.append(
            "1. INVESTIGATE SRM — Do not ship until the sample ratio mismatch is resolved. "
            "Check assignment logs, cookie handling, and eligibility filters."
        )
    if ship == "ship":
        rec.append(
            f"1. Ship treatment — {d.metric_display_name} improved {d.delta_pp:+.2f}pp "
            f"(p={d.p_value:.4f}). Plan a staged rollout and monitor guardrail metrics."
        )
    elif ship == "do_not_ship":
        rec.append(
            "1. Do not ship — the primary metric did not improve. "
            "Archive the hypothesis and document learnings."
        )
    elif ship == "extend":
        rec.append(
            f"1. Extend experiment — insufficient power ({d.n_control + d.n_treatment:,} obs). "
            "Calculate required sample size and set a new end date."
        )

    if result.slice_findings:
        top = max(result.slice_findings, key=lambda s: abs(s.delta.delta_pp))
        rec.append(
            f"2. Investigate heterogeneous effect in {top.dimension_name}={top.dimension_value} "
            f"(Δ={top.delta.delta_pp:+.3f}pp). Consider a targeted follow-up experiment for this segment."
        )

    rec.append(
        "3. Record experiment in the Learnings Repository with hypothesis, outcome, "
        "key insight, and recommended follow-up. Tag with experiment type and funnel stage."
    )

    if causal_estimates:
        if any(e.p_value < 0.05 for e in causal_estimates):
            rec.append(
                "4. Causal estimates corroborate the A/B result — use them in the "
                "stakeholder presentation to strengthen confidence in the finding."
            )
        else:
            rec.append(
                "4. Causal estimates are inconclusive — do not use them as primary evidence. "
                "The A/B result remains the authoritative signal."
            )

    return "\n".join(rec[:5])


# ─────────────────────────────────────────────────────────────────────────────
# ENHANCED PDF REPORT ASSEMBLER
# ─────────────────────────────────────────────────────────────────────────────


def generate_enhanced_report(
    result,
    causal_estimates: List[Any] = None,
    bayesian: Optional[Dict] = None,
    llm=None,
    output_path: Optional[str] = None,
    include_charts: bool = True,
) -> str:
    if output_path is None:
        from continum.paths import new_run_dir

        run_dir = new_run_dir("experiment_analysis")
        output_path = os.path.join(run_dir, "experiment_report.pdf")
    from continum.userui.pdf import render_document_pdf

    causal_estimates = causal_estimates or []
    d = result.primary_delta

    # ── Build each section ────────────────────────────────────────────────────
    exec_narrative = generate_executive_narrative(result, causal_estimates, bayesian, llm)
    next_recs = generate_next_recommendations(result, causal_estimates, llm)

    primary_section = (
        f"Metric: {d.metric_display_name}\n"
        f"Control: {d.rate_control:.4%} ({d.n_control:,} observations)\n"
        f"Treatment: {d.rate_treatment:.4%} ({d.n_treatment:,} observations)\n"
        f"Absolute lift: {d.delta_pp:+.4f}pp\n"
        f"Relative lift: {d.delta_rel:+.1%}\n"
        f"p-value: {d.p_value:.6f}\n"
        f"95% Confidence interval: [{d.ci_lo*100:+.4f}pp, {d.ci_hi*100:+.4f}pp]\n"
        f"Result: {'SIGNIFICANT' if d.is_significant else 'NOT SIGNIFICANT'} at α={d.alpha}\n"
        f"SRM: {'DETECTED (p=' + str(round(result.srm_p_value, 4)) + ')' if result.srm_detected else 'Clean'}\n"
        f"Verdict: {result.verdict.value}\n"
        f"Recommendation: {result.ship_recommendation.value}"
    )

    slice_section = ""
    if result.slice_findings:
        lines = []
        for s in sorted(result.slice_findings, key=lambda x: abs(x.delta.delta_pp), reverse=True)[
            :10
        ]:
            pf = " [PARADOX]" if s.simpsons_paradox_flag else ""
            sig = "✅" if s.is_heterogeneous else "—"
            lines.append(
                f"{sig} {s.dimension_name}={s.dimension_value}  "
                f"Δ={s.delta.delta_pp:+.4f}pp  p={s.delta.p_value:.4f}  n={s.n_slice:,}{pf}"
            )
        slice_section = "\n".join(lines)
    else:
        slice_section = "No segment slices with sufficient sample size."

    causal_section = ""
    if causal_estimates:
        parts = []
        for e in causal_estimates:
            narr = generate_causal_narrative(e, d, llm)
            parts.append(f"[{e.method}] estimate={e.estimate:+.4f}  p={e.p_value:.4f}\n{narr}")
        causal_section = "\n\n".join(parts)
    else:
        causal_section = "No causal estimates were computed for this experiment."

    bayesian_section = ""
    if bayesian:
        bayesian_section = (
            f"P(treatment > control): {bayesian.get('prob_treat_better', 0):.4f}\n"
            f"P(harm): {bayesian.get('prob_harm', 0):.4f}\n"
            f"HDI (95%): [{bayesian.get('hdi_lo_pp', 0):+.4f}pp, {bayesian.get('hdi_hi_pp', 0):+.4f}pp]\n"
            f"Expected loss (ship): {bayesian.get('expected_loss_ship', 0):.6f}\n"
            f"Expected loss (hold): {bayesian.get('expected_loss_hold', 0):.6f}\n"
            f"Decision: {bayesian.get('decision', 'n/a')}"
        )

    appendix = (
        f"Analysis method: {result.analysis_method}\n"
        f"Analyst: {result.analyst}\n"
        f"Analysed at: {result.analysed_at.isoformat()}\n"
        f"Total observations: {d.n_control + d.n_treatment:,}\n"
        f"Effect size (Cohen's h): {d.effect_size:.4f}\n"
        f"Number of segment slices: {len(result.slice_findings)}\n"
        f"Causal methods run: {len(causal_estimates)}\n"
        f"Guardrail violations: {len(result.guardrail_violations)}"
    )

    sections = OrderedDict(
        [
            ("EXECUTIVE SUMMARY", exec_narrative),
            ("PRIMARY METRIC RESULTS", primary_section),
            ("SEGMENT ANALYSIS", slice_section),
            ("CAUSAL CORROBORATION", causal_section),
        ]
    )
    if bayesian_section:
        sections["BAYESIAN ANALYSIS"] = bayesian_section
    sections["NEXT STEPS & RECOMMENDATIONS"] = next_recs
    sections["APPENDIX — STATISTICAL DETAILS"] = appendix

    out = render_document_pdf(
        title=f"Experiment Report: {result.experiment_name}",
        subtitle=f"Verdict: {result.verdict.value.upper()}  ·  "
        f"Recommendation: {result.ship_recommendation.value.replace('_', ' ').upper()}",
        sections=sections,
        output_path=output_path,
        metadata={
            "Experiment": result.experiment_name,
            "Primary metric": d.metric_display_name,
            "Δ (lift)": f"{d.delta_pp:+.4f}pp",
            "p-value": f"{d.p_value:.6f}",
            "Significant": str(d.is_significant),
            "Recommendation": result.ship_recommendation.value,
        },
    )
    logger.info("Enhanced report written → %s", out)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# DECISION MEMO
# ─────────────────────────────────────────────────────────────────────────────


def generate_decision_memo(result, llm=None) -> str:
    d = result.primary_delta
    ship = result.ship_recommendation.value.replace("_", " ").upper()

    if llm is not None:
        context = (
            f"Experiment: {result.experiment_name}\n"
            f"Δ={d.delta_pp:+.4f}pp, p={d.p_value:.4f}, "
            f"significant={d.is_significant}, "
            f"recommendation={result.ship_recommendation.value}\n"
            f"Blockers: {result.ship_blockers}\n"
            f"SRM: {result.srm_detected}"
        )
        prompt = (
            "Write a 4-sentence decision memo for a VP of Product. "
            "Format: (1) What we tested. (2) What happened. "
            "(3) The recommendation and key reason. (4) Risk or caveat if any. "
            "Plain English. Numbers only, no percentages expressed as decimals. "
            f"DATA:\n{context}"
        )
        try:
            return str(llm.ask(prompt))
        except Exception as e:
            logger.warning("Decision memo LLM failed: %s", e)

    sig = (
        "improved"
        if d.is_significant and d.delta_pp > 0
        else "declined" if d.is_significant and d.delta_pp < 0 else "did not significantly change"
    )
    return (
        f"We tested {result.experiment_name} and measured its impact on {d.metric_display_name}. "
        f"The metric {sig} by {abs(d.delta_pp):.2f}pp (p={d.p_value:.4f}). "
        f"Recommendation: {ship}{' — ' + result.ship_blockers[0] if result.ship_blockers else '.'}. "
        f"{'SRM was detected — interpret with caution.' if result.srm_detected else 'No data quality issues were found.'}"
    )


__all__ = [
    "generate_executive_narrative",
    "generate_causal_narrative",
    "generate_next_recommendations",
    "generate_enhanced_report",
    "generate_decision_memo",
]
