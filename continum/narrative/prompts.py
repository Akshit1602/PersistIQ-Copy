from __future__ import annotations
import textwrap
from typing import Any, List, Optional

_SYSTEM_PROMPT = (
    "You are the lead data science & product analytics expert providing business-level insights and experiment readouts. "
    "Write in plain business English. No markdown symbols (no #, **, *, >). "
    "Be specific — use the numbers provided. Do not add generic disclaimers. "
    "Keep sentences short and direct. Never make up numbers not in the context."
)


def build_experiment_readout_prompt(
    result: Any,
    causal_estimates: Optional[List] = None,
    prior_learnings: Optional[List[dict]] = None,
    concurrent_experiments: Optional[List[str]] = None,
) -> str:
    context = result.to_llm_context()
    if causal_estimates:
        context += "\n\nCAUSAL ESTIMATES:\n" + "".join(e.to_llm_context() + "\n" for e in causal_estimates)
    if prior_learnings:
        context += "\n\nRELEVANT PRIOR LEARNINGS:\n"
        for l in prior_learnings[:3]:
            context += f"  [{l.get('confidence','?').upper()}] {l.get('statement','')}\n"
    if concurrent_experiments:
        context += f"\n\nCONCURRENT EXPERIMENTS: {', '.join(concurrent_experiments)}\n"

    instruction = textwrap.dedent("""
        Based on the experiment result above, write a 4-6 sentence executive readout covering:
        1. The key result and whether it is statistically significant (use exact delta and p-value).
        2. The ship recommendation and the primary reason.
        3. Any guardrail concerns — if none, say so explicitly.
        4. The most important dimensional finding (if any).
        5. One sentence on what this result tells us about the underlying hypothesis.
        If prior learnings are listed, note whether this result confirms or contradicts them.
    """).strip()
    return f"{context}\n\n{instruction}"


def build_anomaly_narrative_prompt(anomalies: List[Any], pipeline_status: str = "UNKNOWN") -> str:
    n_crit = sum(1 for a in anomalies if a.severity.value == "critical")
    n_warn = sum(1 for a in anomalies if a.severity.value == "warning")
    context = (
        f"MONITORING REPORT\nStatus: {pipeline_status}\n"
        f"Critical: {n_crit}  Warning: {n_warn}\n\nANOMALY DETAILS:\n"
    )
    for a in anomalies[:10]:
        context += a.to_llm_context() + "\n"
    instruction = (
        "Write a 4-6 sentence monitoring summary: (1) overall health, "
        "(2) most urgent finding and likely cause, "
        "(3) whether anomalies overlap with running experiments, "
        "(4) the single most important immediate action. No emojis."
    )
    return f"{context}\n{instruction}"


def build_power_analysis_prompt(power: Any) -> str:
    return (
        f"{power.to_llm_context()}\n\n"
        "Write a 3-4 sentence plain-English summary: (1) what the numbers mean practically, "
        "(2) business risk of running shorter or longer, "
        "(3) one specific recommendation for the experiment team."
    )


def build_opportunity_sizing_prompt(sizing: Any) -> str:
    return (
        f"{sizing.to_llm_context()}\n\n"
        "Write a 3-4 sentence business case: (1) revenue opportunity in dollar terms over 12 months, "
        "(2) what the team needs to achieve the IOR improvement, "
        "(3) one specific experiment recommendation."
    )


def build_learning_extraction_prompt(result: Any, causal_estimates: Optional[List] = None) -> str:
    context = result.to_llm_context()
    if causal_estimates:
        context += "\n\nCAUSAL ESTIMATES:\n" + "\n".join(e.to_llm_context() for e in causal_estimates)
    instruction = textwrap.dedent("""
        Extract 1-2 generalisable learnings from this experiment.
        For each learning, respond in this exact format:
        LEARNING_START
        Statement: <generalisable insight>
        Domain: <pricing | UX | onboarding | conversion | retention | engagement>
        Confidence: <confirmed | probable | tentative>
        Evidence: <causal | correlational>
        Applicable_metrics: <comma-separated>
        Applicable_segments: <comma-separated, or "all">
        LEARNING_END
    """).strip()
    return f"{context}\n\n{instruction}"


def parse_learnings_from_llm_output(raw: str) -> list:
    import re
    learnings = []
    for block in re.findall(r"LEARNING_START(.*?)LEARNING_END", raw, re.DOTALL):
        learning = {}
        for line in block.strip().split("\n"):
            if ":" in line:
                k, _, v = line.partition(":")
                learning[k.strip().lower().replace(" ", "_")] = v.strip()
        if learning.get("statement"):
            learnings.append(learning)
    return learnings


def template_experiment_readout(result: Any) -> str:
    d   = result.primary_delta
    sig = "significant" if d.is_significant else "not significant"
    dp  = f"{d.delta_pp:+.2f}pp" if d.delta_pp is not None else f"Δ={d.delta_abs:+.4f}"
    ship = result.ship_recommendation.value.replace("_", " ").title()
    parts = [
        f"Experiment '{result.experiment_name}': {d.metric_display_name} moved {dp} "
        f"({sig}, p={d.p_value:.4f}). Verdict: {result.verdict.value.upper()}.",
        f"Recommendation: {ship}.",
    ]
    if result.guardrail_violations:
        parts.append(f"{len(result.guardrail_violations)} guardrail violation(s): "
                     + "; ".join(v.guardrail_name for v in result.guardrail_violations) + ".")
    if result.srm_detected:
        parts.append(f"WARNING: SRM detected (p={result.srm_p_value:.4f}).")
    return " ".join(parts)


def template_anomaly_readout(anomalies: list) -> str:
    if not anomalies:
        return "No anomalies detected. All monitored metrics are within expected bounds."
    n_crit = sum(1 for a in anomalies if a.severity.value == "critical")
    n_warn = sum(1 for a in anomalies if a.severity.value == "warning")
    top = anomalies[0]
    return (
        f"Pipeline status: {'CRITICAL' if n_crit > 0 else 'WARNING'}. "
        f"{n_crit} critical, {n_warn} warnings. "
        f"Most urgent: {top.anomaly_type} on {top.metric_affected} "
        f"({top.pct_change:+.1f}%, z={top.deviation_z_score:+.2f}). "
        f"Action: {top.recommended_action}."
    )


__all__ = [
    "_SYSTEM_PROMPT",
    "build_experiment_readout_prompt", "build_anomaly_narrative_prompt",
    "build_power_analysis_prompt", "build_opportunity_sizing_prompt",
    "build_learning_extraction_prompt", "parse_learnings_from_llm_output",
    "template_experiment_readout", "template_anomaly_readout",
]
