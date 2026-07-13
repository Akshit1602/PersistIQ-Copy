from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional

logger = logging.getLogger("continum.askdata.narrative_runtime")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _g(obj, *keys, default=None):
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


def _pick(*options: str) -> str:
    return random.choice(options)


# ─────────────────────────────────────────────────────────────────────────────
# NARRATIVE RUNTIME
# ─────────────────────────────────────────────────────────────────────────────


class NarrativeRuntime:

    def __init__(self, bus=None, session=None, memory=None):
        self.bus = bus
        self.session = session
        self.memory = memory

    # ── After a module completes ───────────────────────────────────────────────

    def after_module(self, module_key: str, result: Any = None) -> str:
        fn = _MODULE_NARRATORS.get(module_key)
        if fn:
            text = fn(result, self.session, self.memory)
        else:
            text = self._generic_completion(module_key, result)

        self._publish(text, source=module_key)
        return text

    def _generic_completion(self, module_key: str, result: Any) -> str:
        name = module_key.replace("_", " ")
        return f"{_pick('Finished', 'Completed', 'Done with')} {name}."

    # ── Transitions ────────────────────────────────────────────────────────────

    def transition(self, from_module: str, to_module: str) -> str:
        key = (from_module, to_module)
        text = _TRANSITIONS.get(key)
        if not text:
            from_name = from_module.replace("_", " ")
            to_name = to_module.replace("_", " ")
            text = f"With {from_name} behind us, let's move on to {to_name}."
        self._publish(text, source="transition")
        return text

    # ── Idle thoughts ──────────────────────────────────────────────────────────

    def idle_thought(self) -> str:
        thoughts = self._gather_idle_thoughts()
        if not thoughts:
            return ""
        text = random.choice(thoughts)
        self._publish(text, source="observation")
        return text

    def _gather_idle_thoughts(self) -> List[str]:
        thoughts = []
        s = self.session
        b = self.bus

        if s is None:
            return ["Ready. Select an experiment to begin."]

        exp = s.active_experiment
        metrics = s.active_metrics
        n_runs = len(s.execution_history)
        result = s.get("experiment_result")

        # No experiment selected
        if not exp:
            thoughts.extend(
                [
                    "No experiment selected. Start by loading data or picking an experiment from the dropdown.",
                    "The schema discovery module can help map your data before running any analysis.",
                    "Once an experiment is selected, I can tell you whether it's significant and why.",
                ]
            )
            return thoughts

        # Experiment selected, no analysis run
        if exp and not s.last_run("experiment_analysis"):
            thoughts.extend(
                [
                    f"Experiment '{exp}' is loaded but not yet analysed. Run the A/B Readout when ready.",
                    f"I haven't seen the results for '{exp}' yet. The A/B Readout will tell us whether it moved the needle.",
                    f"'{exp}' is selected. When you run the readout, I'll tell you whether the effect is real.",
                ]
            )

        # Analysis run, results available
        if result:
            primary = _g(result, "primary_delta")
            dp = float(_g(primary, "delta_pp") or 0)
            pv = float(_g(primary, "p_value") or 1)
            sig = bool(_g(primary, "is_significant") or False)
            srm = bool(_g(result, "srm_detected") or False)

            if srm:
                thoughts.append(
                    f"A sample ratio mismatch is active on '{exp}'. "
                    "This means the assignment mechanism may be broken — results here are not trustworthy."
                )
            elif sig and dp > 0:
                thoughts.append(
                    f"'{exp}' is showing a {dp:+.2f}pp lift (p={pv:.4f}). "
                    f"That's a {_pick('promising', 'meaningful', 'real')} result. "
                    "Check segment breakdown to understand who it's working for."
                )
            elif sig and dp < 0:
                thoughts.append(
                    f"'{exp}' has a {dp:+.2f}pp regression (p={pv:.4f}). "
                    "Worth understanding what's driving this before making any ship decision."
                )
            elif not sig:
                thoughts.append(
                    f"'{exp}' hasn't reached significance (p={pv:.4f}). "
                    "Either the effect is too small, or the experiment is underpowered."
                )

        # Warnings from bus
        if b:
            warnings = b.warnings()
            if warnings:
                w = warnings[-1]
                thoughts.append(f"Active warning from {w.source_module}: {w.message}")

        # Memory observations
        if self.memory and n_runs > 0:
            try:
                good = self.memory.get_successful_metrics(limit=1)
                if good:
                    m = good[0]
                    if metrics and m["metric_name"].lower() in [x.lower() for x in metrics]:
                        thoughts.append(
                            f"{m['metric_name']} has been significant in "
                            f"{m['n_experiments']} past experiment(s) — good choice as primary metric."
                        )
            except Exception:
                pass

        # Phase recommendations
        history_modules = {r.module for r in s.execution_history}
        if "experiment_analysis" in history_modules and "causal_analysis" not in history_modules:
            thoughts.append(
                "The A/B readout is done. Running causal analysis next would confirm whether the effect is truly causal."
            )
        if "causal_analysis" in history_modules and "learnings_repository" not in history_modules:
            thoughts.append(
                "Causal analysis complete. Consider storing findings to the learnings repository before moving on."
            )

        return thoughts or [f"Working in session {s.session_id}. {n_runs} module(s) run."]

    # ── Session opening ────────────────────────────────────────────────────────

    def open_session(self) -> str:
        s = self.session
        if s is None:
            return "Session started."

        n_runs = len(s.execution_history)
        exp = s.active_experiment
        n_mem = self.memory.experiment_count() if self.memory else 0

        if n_runs == 0 and not exp:
            text = (
                f"Session {s.session_id} open. "
                f"{'I have ' + str(n_mem) + ' past experiment(s) in memory to draw from. ' if n_mem else ''}"
                "Select an experiment or run schema discovery to get started."
            )
        elif n_runs > 0:
            last = s.execution_history[-1]
            text = (
                f"Resuming session {s.session_id}. "
                f"Last action: {last.module} ({last.elapsed_s:.1f}s). "
                f"{exp and 'Active experiment: ' + exp + '.' or ''}"
            )
        else:
            text = f"Session {s.session_id} open. " f"Experiment '{exp}' selected. Ready."

        self._publish(text, source="session")
        return text

    # ── Internal ───────────────────────────────────────────────────────────────

    def _publish(self, text: str, source: str = "narrative") -> None:
        if self.bus and text:
            try:
                from continum.insights.insight_bus import InsightSeverity, InsightType

                self.bus.emit(
                    source_module=source,
                    message=text,
                    insight_type=InsightType.NARRATIVE,
                    severity=InsightSeverity.INFO,
                )
            except Exception:
                pass

    def get_stream(self, n: int = 12) -> List[Dict]:
        if not self.bus:
            return []
        try:
            from continum.insights.insight_bus import InsightType

            items = self.bus.by_type(InsightType.NARRATIVE)[-n:]
            return [
                {
                    "text": i.message,
                    "source": i.source_module,
                    "created_at": i.created_at[:19],
                }
                for i in reversed(items)
            ]
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────────────────────
# MODULE-SPECIFIC NARRATORS
# ─────────────────────────────────────────────────────────────────────────────


def _narrate_schema_discovery(result, session, memory) -> str:
    tables = _g(result, "tables_discovered", default=0) or 0
    metrics = _g(result, "metrics_inferred", default=[]) or []
    n_m = len(metrics) if isinstance(metrics, list) else 0
    return (
        f"Schema discovery mapped {tables} table(s). "
        f"{'Inferred ' + str(n_m) + ' candidate metric(s). ' if n_m else ''}"
        f"The semantic layer now knows how to talk to your data."
    )


def _narrate_experiment_analysis(result, session, memory) -> str:
    r = _g(result, "result") or result
    primary = _g(r, "primary_delta")
    dp = float(_g(primary, "delta_pp") or 0)
    pv = float(_g(primary, "p_value") or 1)
    sig = bool(_g(primary, "is_significant") or False)
    srm = bool(_g(r, "srm_detected") or False)
    exp = _g(r, "experiment_name") or (session.active_experiment if session else "")

    if srm:
        return (
            f"Results are in for '{exp}', but there's a sample ratio mismatch. "
            "The assignment mechanism appears broken — don't draw conclusions from this data yet."
        )
    if sig and dp > 0:
        return (
            f"'{exp}' shows a significant {dp:+.3f}pp lift (p={pv:.4f}). "
            f"This is a real effect. Now let's understand what's driving it — "
            "check the segment breakdown for heterogeneity."
        )
    if sig and dp < 0:
        return (
            f"'{exp}' has a significant regression: {dp:+.3f}pp (p={pv:.4f}). "
            "Before any ship decision, I'd want to understand whether a specific segment is pulling it down."
        )
    return (
        f"'{exp}' hasn't reached significance (Δ={dp:+.3f}pp, p={pv:.4f}). "
        "The effect is either too small to detect with current sample, or it's genuinely null."
    )


def _narrate_causal_analysis(result, session, memory) -> str:
    estimates = _g(result, "estimates", default=[]) or []
    n = len(estimates)
    if not n:
        return "Causal analysis completed. No estimates were produced — check data requirements."
    methods = [_g(e, "method", default="?") for e in estimates[:3]]
    agreement = _check_estimate_agreement(estimates)
    return (
        f"Ran {n} causal method(s): {', '.join(methods)}. "
        f"{agreement} "
        "When methods agree, the causal inference is more trustworthy."
    )


def _check_estimate_agreement(estimates: list) -> str:
    if len(estimates) < 2:
        return ""
    sigs = [bool(_g(e, "is_significant") or False) for e in estimates]
    ests = [float(_g(e, "estimate") or 0) for e in estimates]
    if all(sigs):
        avg_est = sum(ests) / len(ests)
        return f"All methods agree: consistent estimate of {avg_est:+.4f}."
    elif any(sigs):
        return "Methods are mixed — some significant, some not. Treat with caution."
    return "No method reached significance."


def _narrate_power_calculator(result, session, memory) -> str:
    n_req = _g(result, "n_total") or _g(result, "result", default={})
    if hasattr(n_req, "n_total"):
        n_req = n_req.n_total
    if isinstance(n_req, dict):
        n_req = n_req.get("n_total")
    n_req = int(n_req or 0)
    days = _g(result, "days_required") or 0
    mde = _g(result, "mde_rel") or 0

    if n_req:
        return (
            f"Power analysis done. To detect a {float(mde):.1%} relative lift "
            f"you'll need {n_req:,} users ({days} day(s) at current traffic). "
            "If the experiment is already live and below this, it's likely underpowered."
        )
    return "Power analysis completed. Check the requirements against your current traffic."


def _narrate_health_monitor(result, session, memory) -> str:
    violations = _g(result, "guardrail_violations", default=[]) or []
    srm = _g(result, "srm_detected", default=False)
    n_v = len(violations)

    if srm:
        return (
            "Health check flagged a sample ratio mismatch. "
            "Experiment assignment is unbalanced — this needs immediate investigation."
        )
    if n_v:
        names = [_g(v, "guardrail_name", default="?") for v in violations[:2]]
        return (
            f"{n_v} guardrail violation(s): {', '.join(names)}. "
            "These regressions must be resolved before shipping."
        )
    return (
        "Health check passed. No SRM, no guardrail violations. "
        "The experiment is running cleanly."
    )


def _narrate_opportunity_sizing(result, session, memory) -> str:
    opp = _g(result, "annual_opportunity_usd") or _g(result, "opportunity_usd")
    if opp:
        return (
            f"Opportunity sized at ${float(opp):,.0f} annually. "
            "This is the prize if the experiment succeeds at the expected lift."
        )
    return "Opportunity sizing complete. Review the revenue model in the results."


def _narrate_learnings_repository(result, session, memory) -> str:
    exp = session.active_experiment if session else "the experiment"
    return (
        f"Findings from '{exp}' stored to the learnings repository. "
        "Future experiments will be able to draw on this as prior knowledge."
    )


_MODULE_NARRATORS = {
    "schema_discovery": _narrate_schema_discovery,
    "experiment_analysis": _narrate_experiment_analysis,
    "causal_analysis": _narrate_causal_analysis,
    "power_calculator": _narrate_power_calculator,
    "health_monitor": _narrate_health_monitor,
    "opportunity_sizing": _narrate_opportunity_sizing,
    "learnings_repository": _narrate_learnings_repository,
}


# ─────────────────────────────────────────────────────────────────────────────
# TRANSITIONS
# ─────────────────────────────────────────────────────────────────────────────

_TRANSITIONS = {
    (
        "schema_discovery",
        "power_calculator",
    ): "With the schema mapped, we can now size the experiment properly.",
    (
        "schema_discovery",
        "opportunity_sizing",
    ): "Schema's clear. Let's quantify the revenue opportunity before committing to an experiment.",
    (
        "opportunity_sizing",
        "power_calculator",
    ): "Opportunity is sized. Now we need to know how long to run the experiment.",
    (
        "power_calculator",
        "brief_generator",
    ): "Sample size is set. Time to formalise the hypothesis into a brief.",
    (
        "brief_generator",
        "health_monitor",
    ): "Brief is ready. If the experiment is live, let's check its health.",
    ("health_monitor", "experiment_analysis"): "Health looks good. Moving to the full readout.",
    (
        "experiment_analysis",
        "causal_analysis",
    ): "A/B analysis is done. Let's validate the finding with causal methods.",
    (
        "causal_analysis",
        "learnings_repository",
    ): "Causal estimates are in. Let's store this before we move on.",
}


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

_NARRATIVE: Optional[NarrativeRuntime] = None


def get_narrative(bus=None, session=None, memory=None) -> NarrativeRuntime:
    global _NARRATIVE
    if _NARRATIVE is None:
        _NARRATIVE = NarrativeRuntime(bus=bus, session=session, memory=memory)
    else:
        if bus is not None:
            _NARRATIVE.bus = bus
        if session is not None:
            _NARRATIVE.session = session
        if memory is not None:
            _NARRATIVE.memory = memory
    return _NARRATIVE


__all__ = [
    "NarrativeRuntime",
    "get_narrative",
]
