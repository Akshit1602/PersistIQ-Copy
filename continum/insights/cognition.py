from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("continum.cognition")


# ─────────────────────────────────────────────────────────────────────────────
# COGNITIVE STATE — accumulates knowledge across module runs
# ─────────────────────────────────────────────────────────────────────────────

class CognitiveState:

    def __init__(self, session_id: str = "default"):
        self.session_id      = session_id
        self.experiment_name = ""
        self.results:   Dict[str, Any]    = {}    # module_name → result
        self.insights:  List[Dict]        = []    # derived analytical insights
        self.questions: List[str]         = []    # open questions
        self.narrative: List[str]         = []    # running narrative log
        self.causal_chain: List[Dict]     = []    # causal inference chain
        self.decision_state: Dict         = {}    # current decision context
        self._created_at: float           = time.time()

    def update(self, module: str, result: Any, insights: List[Dict] = None) -> None:
        self.results[module] = result
        if insights:
            self.insights.extend(insights)
        logger.debug("Cognition: updated %s (total modules: %d)", module, len(self.results))

    def get_context_for_module(self, module: str) -> Dict:
        ctx: Dict = {
            "experiment_name": self.experiment_name,
            "prior_modules":   list(self.results.keys()),
            "open_questions":  self.questions[:5],
            "current_decision": self.decision_state,
        }
        # Carry forward key numbers
        if "experiment_analysis" in self.results:
            ea = self.results["experiment_analysis"]
            primary = ea.get("primary", {})
            if primary:
                best_trt = max(primary, key=lambda k: primary[k]["delta_pp"], default="")
                if best_trt:
                    ctx["best_treatment"]    = best_trt
                    ctx["best_delta_pp"]     = primary[best_trt]["delta_pp"]
                    ctx["experiment_sig"]    = primary[best_trt]["sig"]
        if "power_calculator" in self.results:
            pc = self.results["power_calculator"]
            ctx["baseline_ior"]   = pc.get("baseline", 0.18)
            ctx["mde_pp"]         = pc.get("mde_abs", 0.01) * 100
        if "causal_analysis" in self.results or "causal_analysis_full" in self.results:
            ca = self.results.get("causal_analysis_full") or self.results.get("causal_analysis", {})
            for method in ["did", "its", "psm"]:
                if method in ca and not ca[method].get("error"):
                    est = (ca[method].get("did_estimate_pp") or
                           ca[method].get("level_change_pp") or
                           ca[method].get("att_pp") or 0)
                    ctx[f"causal_{method}_pp"] = est
        return ctx

    def to_dict(self) -> Dict:
        return {
            "session_id":     self.session_id,
            "experiment":     self.experiment_name,
            "modules_run":    list(self.results.keys()),
            "n_insights":     len(self.insights),
            "n_questions":    len(self.questions),
            "decision_state": self.decision_state,
            "narrative_len":  len(self.narrative),
        }


# ─────────────────────────────────────────────────────────────────────────────
# SESSION REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

_STATES: Dict[str, CognitiveState] = {}


def get_cognitive_state(session_id: str = "default") -> CognitiveState:
    if session_id not in _STATES:
        _STATES[session_id] = CognitiveState(session_id)
    return _STATES[session_id]


# ─────────────────────────────────────────────────────────────────────────────
# MODULE POST-PROCESSOR — runs after every module completes
# ─────────────────────────────────────────────────────────────────────────────

def post_process_module_result(
    module_name: str,
    result:      Any,
    db:          Any  = None,
    llm:         Any  = None,
    bus:         Any  = None,
    session_id:  str  = "default",
) -> Dict:
    state = get_cognitive_state(session_id)
    state.update(module_name, result)

    derived: Dict = {"module": module_name, "insights": [], "next_steps": []}

    if not isinstance(result, dict):
        return derived

    # ── Extract signal insights ────────────────────────────────────────────────
    try:
        insights = _extract_insights(module_name, result, state)
        state.insights.extend(insights)
        derived["insights"] = insights
        for ins in insights[:3]:
            if bus is not None:
                _publish_insight(bus, module_name, ins)
    except Exception as e:
        logger.debug("Insight extraction failed: %s", e)

    # ── Generate next steps ────────────────────────────────────────────────────
    try:
        next_steps = _generate_cognition_next_steps(module_name, result, state, llm)
        state.questions.extend([s["reason"] for s in next_steps[:2]])
        derived["next_steps"] = next_steps
        for step in next_steps[:2]:
            if bus is not None:
                _publish_next(bus, module_name, step)
    except Exception as e:
        logger.debug("Next steps generation failed: %s", e)

    # ── Update decision state ──────────────────────────────────────────────────
    if module_name in ("experiment_analysis", "decision_engine"):
        _update_decision_state(state, result)

    # ── Cross-module synthesis ─────────────────────────────────────────────────
    if module_name in ("causal_analysis", "causal_analysis_full", "uplift_modeller"):
        try:
            cross_synthesis = _cross_module_synthesis(state, llm)
            if cross_synthesis:
                derived["cross_synthesis"] = cross_synthesis
                state.narrative.append(cross_synthesis)
                if bus is not None:
                    _publish_narrative(bus, module_name, cross_synthesis)
        except Exception as e:
            logger.debug("Cross-module synthesis failed: %s", e)

    # ── Persist to session ─────────────────────────────────────────────────────
    try:
        from continum.insights.session import get_session
        sess = get_session()
        if sess is not None:
            sess.set(f"cognition_{module_name}", derived)
            sess.set("cognition_state", state.to_dict())
    except Exception:
        pass

    # ── Save learnings if ship decision ───────────────────────────────────────
    if module_name == "decision_engine" and result.get("decision") == "SHIP" and db is not None:
        _auto_record_learning(state, result, db)

    return derived


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHT EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def _extract_insights(module_name: str, result: Dict, state: CognitiveState) -> List[Dict]:
    insights: List[Dict] = []

    if module_name in ("experiment_analysis", "health_monitor"):
        for trt, r in result.get("primary", {}).items():
            if r.get("sig") and r.get("delta_pp", 0) > 0:
                insights.append({
                    "type": "positive_result",
                    "message": f"{trt}: Δ={r['delta_pp']:+.3f}pp (sig, p={r['p_value']:.4f})",
                    "severity": "success",
                    "data": r,
                })
            elif r.get("sig") and r.get("delta_pp", 0) < 0:
                insights.append({
                    "type": "negative_result",
                    "message": f"{trt}: Δ={r['delta_pp']:+.3f}pp (significantly NEGATIVE)",
                    "severity": "error",
                    "data": r,
                })
            elif not r.get("sig"):
                insights.append({
                    "type": "inconclusive",
                    "message": f"{trt}: not significant (p={r['p_value']:.4f}). Need more data.",
                    "severity": "warning",
                })

    if module_name in ("simpsons_paradox", "causal_analysis_full"):
        if result.get("simpsons", {}).get("paradoxes") or result.get("n_paradoxes", 0) > 0:
            paradoxes = (result.get("simpsons", {}).get("paradoxes")
                         or result.get("paradoxes", []))
            for p in paradoxes[:3]:
                insights.append({
                    "type": "simpsons_paradox",
                    "message": f"Simpson's paradox: {p.get('dimension')}={p.get('level')} "
                               f"reverses sign ({p.get('segment_delta_pp',0):+.2f}pp vs "
                               f"{p.get('overall_delta_pp',0):+.2f}pp overall)",
                    "severity": "critical" if p.get("severity") == "critical" else "warning",
                    "data": p,
                })

    if module_name == "uplift_modeller":
        qini = result.get("qini_coefficient", 0)
        top_q = (result.get("quartile_breakdown") or [{}])[-1]
        insights.append({
            "type": "uplift_model",
            "message": (f"Qini={qini:.4f}. Top-quartile Δ={top_q.get('delta_pp',0):+.3f}pp. "
                        f"{'Model beats random targeting.' if qini > 0 else 'Model performs at chance.'}"),
            "severity": "success" if qini > 0.01 else "info",
        })

    if module_name in ("health_monitor",):
        if result.get("srm_flag"):
            insights.append({
                "type": "srm",
                "message": f"SRM detected (p={result.get('srm_p', 0):.4f}). "
                           "Statistical inference is INVALID. Pause experiment.",
                "severity": "critical",
            })
        if result.get("guardrail_violations"):
            insights.append({
                "type": "guardrail_violation",
                "message": f"{len(result['guardrail_violations'])} guardrail violation(s). "
                           "Review immediately.",
                "severity": "error",
            })

    if module_name == "causal_analysis_full":
        did = result.get("did", {})
        if did and not did.get("error"):
            insights.append({
                "type": "causal_did",
                "message": (f"DiD estimate: {did.get('did_estimate_pp',0):+.3f}pp "
                            f"({'sig' if did.get('is_significant') else 'n.s.'}). "
                            f"PT: {'✓' if did.get('parallel_trends_ok') else '✗'}"),
                "severity": "success" if did.get("is_significant") else "info",
            })

    return insights


# ─────────────────────────────────────────────────────────────────────────────
# COGNITION-LEVEL NEXT STEPS
# ─────────────────────────────────────────────────────────────────────────────

_COGNITION_CHAIN: Dict[str, List[Dict]] = {
    "power_calculator": [
        {"module": "opportunity_sizing",  "reason": "Size the GMV opportunity at MDE", "priority": 1},
        {"module": "brief_generator",     "reason": "Generate PRD brief with power inputs", "priority": 2},
    ],
    "opportunity_sizing": [
        {"module": "brief_generator",     "reason": "Convert sizing into experiment brief", "priority": 1},
        {"module": "metrics_and_tracking","reason": "Define KPIs grounded in the sizing model", "priority": 2},
    ],
    "brief_generator": [
        {"module": "metrics_and_tracking","reason": "Define KPIs + tracking plan", "priority": 1},
        {"module": "audience_selection",  "reason": "Select balanced audience", "priority": 2},
    ],
    "metrics_and_tracking": [
        {"module": "audience_selection",  "reason": "Select audience after KPIs are set", "priority": 1},
    ],
    "audience_selection": [
        {"module": "health_monitor",      "reason": "Monitor SRM and guardrails once live", "priority": 1},
    ],
    "health_monitor": [
        {"module": "sequential_testing",  "reason": "Check always-valid p-values for early stopping", "priority": 1},
        {"module": "anomaly_synthesis",   "reason": "Synthesise anomalies from health data", "priority": 2},
    ],
    "sequential_testing": [
        {"module": "experiment_analysis", "reason": "Full analysis after sufficient data", "priority": 1},
    ],
    "experiment_analysis": [
        {"module": "causal_analysis_full","reason": "Strengthen causal claim with DiD/PSM", "priority": 1},
        {"module": "simpsons_paradox",    "reason": "Check for reversed effects in segments", "priority": 2},
        {"module": "root_cause",          "reason": "Explain unexpected segment patterns", "priority": 3},
    ],
    "causal_analysis_full": [
        {"module": "roi_tracker",         "reason": "Quantify post-ship incremental GMV", "priority": 1},
        {"module": "uplift_modeller",     "reason": "Model per-user treatment effect for targeting", "priority": 2},
    ],
    "simpsons_paradox": [
        {"module": "causal_analysis_full","reason": "Re-run causal analysis stratified by confound", "priority": 1},
        {"module": "decision_engine",     "reason": "Factor paradox into ship recommendation", "priority": 2},
    ],
    "roi_tracker": [
        {"module": "uplift_modeller",     "reason": "Model targeted rollout to amplify ROI", "priority": 1},
        {"module": "learnings_repository","reason": "Record ROI outcome for future experiments", "priority": 2},
    ],
    "uplift_modeller": [
        {"module": "decision_engine",     "reason": "Optimise targeting from uplift scores", "priority": 1},
    ],
    "decision_engine": [
        {"module": "learnings_repository","reason": "Record decision + learnings", "priority": 1},
        {"module": "cross_experiment_learning","reason": "Check if pattern matches portfolio", "priority": 2},
    ],
}


def _generate_cognition_next_steps(
    module_name: str,
    result:      Dict,
    state:       CognitiveState,
    llm:         Any,
) -> List[Dict]:
    base_steps = _COGNITION_CHAIN.get(module_name, [])
    steps      = [s for s in base_steps if s["module"] not in state.results]

    # Signal-driven overrides
    if result.get("srm_flag"):
        steps.insert(0, {"module": "health_monitor", "reason": "SRM detected — pause and investigate", "priority": 0})
    if result.get("simpsons", {}).get("paradoxes"):
        if "causal_analysis_full" not in state.results:
            steps.insert(0, {"module": "causal_analysis_full",
                             "reason": "Paradox detected — strengthen causal claim before deciding",
                             "priority": 0})

    # LLM-suggested additional step
    if llm is not None and result and module_name in (
        "experiment_analysis", "causal_analysis_full", "health_monitor"
    ):
        try:
            ctx = state.get_context_for_module(module_name)
            summary = str({k: v for k, v in result.items()
                           if k not in ("primary", "slices")})[:300]
            resp = str(llm.ask(
                f"After running '{module_name}' with result summary:\n{summary}\n"
                f"Current context: {ctx}\n\n"
                f"Suggest ONE specific analytical follow-up not in this list: "
                f"{[s['module'] for s in steps[:4]]}.\n"
                "Format: module_key|one-sentence reason"
            ))
            if "|" in resp:
                parts = resp.strip().split("|", 1)
                m_key = parts[0].strip().lower().replace(" ", "_")
                reason = parts[1].strip() if len(parts) > 1 else ""
                if m_key and reason and m_key not in [s["module"] for s in steps]:
                    steps.append({"module": m_key, "reason": reason,
                                  "priority": len(steps) + 1, "llm_suggested": True})
        except Exception as e:
            logger.debug("LLM next step suggestion failed: %s", e)

    return sorted(steps, key=lambda x: x.get("priority", 99))[:5]


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-MODULE SYNTHESIS
# ─────────────────────────────────────────────────────────────────────────────

def _cross_module_synthesis(state: CognitiveState, llm: Any) -> str:
    if len(state.results) < 3 or llm is None:
        return ""

    # Build compact summary
    summary_parts = []
    ea = state.results.get("experiment_analysis", {})
    if ea.get("primary"):
        for trt, r in list(ea["primary"].items())[:2]:
            summary_parts.append(f"AB test: {trt} Δ={r['delta_pp']:+.3f}pp "
                                  f"({'sig' if r['sig'] else 'n.s.'})")

    ca = state.results.get("causal_analysis_full") or state.results.get("causal_analysis", {})
    for method in ["did", "its", "psm"]:
        m = ca.get(method, {})
        if m and not m.get("error"):
            est = m.get("did_estimate_pp") or m.get("level_change_pp") or m.get("att_pp") or 0
            sig = m.get("is_significant") or m.get("level_significant")
            summary_parts.append(f"{method.upper()}: {est:+.3f}pp ({'sig' if sig else 'n.s.'})")

    roi = state.results.get("roi_tracker", {}).get("roi", {})
    if roi and not roi.get("error"):
        summary_parts.append(f"ROI: Δ={roi.get('delta_ior',0)*100:+.3f}pp  "
                              f"12m GMV=${roi.get('12m_gmv_central',0):,.0f}")

    if not summary_parts:
        return ""

    summary = "\n".join(f"  • {s}" for s in summary_parts)
    try:
        return str(llm.ask(
            f"Cross-module analytical synthesis for experiment '{state.experiment_name}'.\n\n"
            f"Evidence accumulated:\n{summary}\n\n"
            "In 2-3 sentences: (1) Do the AB test and causal estimates agree? "
            "(2) What does the convergence (or divergence) tell us? "
            "(3) What is the most defensible conclusion from the combined evidence?"
        ))
    except Exception as e:
        logger.debug("Cross-module LLM synthesis failed: %s", e)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# DECISION STATE UPDATER
# ─────────────────────────────────────────────────────────────────────────────

def _update_decision_state(state: CognitiveState, result: Dict) -> None:
    primary = result.get("primary", {})
    if primary:
        state.decision_state.update({
            "decision":   result.get("decision", "unknown"),
            "best_delta": max((r["delta_pp"] for r in primary.values()), default=0),
            "all_sig":    all(r["sig"] for r in primary.values()),
            "any_sig":    any(r["sig"] for r in primary.values()),
        })


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-RECORD LEARNINGS
# ─────────────────────────────────────────────────────────────────────────────

def _auto_record_learning(state: CognitiveState, result: Dict, db: Any) -> None:
    try:
        import pandas as pd
        ea      = state.results.get("experiment_analysis", {})
        primary = ea.get("primary", {})
        best_trt = max(primary, key=lambda k: primary[k]["delta_pp"], default="") if primary else ""
        r        = primary.get(best_trt, {})
        new_id   = f"AUTO_{int(time.time())}"

        learning = {
            "id":                    new_id,
            "experiment_name":       state.experiment_name,
            "ship_decision":         "ship",
            "outcome":               f"Δ={r.get('delta_pp',0):+.3f}pp  p={r.get('p_value',1):.4f}",
            "key_learning":          result.get("rationale", "Significant positive lift."),
            "what_worked":           f"{best_trt} showed {r.get('delta_pp',0):+.3f}pp improvement",
            "what_didnt":            "",
            "recommendation":        "Re-run in adjacent segments that didn't show lift.",
            "follow_ups":            "Monitor IOR weekly for 4 weeks post-ship.",
            "recorded_by":           "auto_cognition",
            "recorded_at":           str(pd.Timestamp.today().date()),
            "tags":                  "auto,ship",
        }

        try:
            existing = db.execute("SELECT * FROM experiment_learnings").df()
        except Exception:
            existing = pd.DataFrame()

        new_df = pd.concat([existing, pd.DataFrame([learning])], ignore_index=True)
        db.register("experiment_learnings", new_df)
        logger.info("Auto-recorded learning %s for %s", new_id, state.experiment_name)
    except Exception as e:
        logger.debug("Auto-record learning failed: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# BUS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _publish_insight(bus: Any, source: str, insight: Dict) -> None:
    try:
        from continum.insights.insight_bus import InsightType, InsightSeverity
        sev_map = {
            "success": InsightSeverity.SUCCESS, "error": InsightSeverity.CRITICAL,
            "critical": InsightSeverity.CRITICAL, "warning": InsightSeverity.WARNING,
            "info": InsightSeverity.INFO,
        }
        bus.emit(source=source,
                 insight_type=InsightType.INFO,
                 severity=sev_map.get(insight.get("severity", "info"), InsightSeverity.INFO),
                 message=insight.get("message", "")[:200])
    except Exception:
        pass


def _publish_next(bus: Any, source: str, step: Dict) -> None:
    try:
        bus.next_step(source=source,
                      message=f"Next: run {step['module']}",
                      detail=step.get("reason", ""))
    except Exception:
        pass


def _publish_narrative(bus: Any, source: str, text: str) -> None:
    try:
        from continum.insights.insight_bus import InsightType, InsightSeverity
        bus.emit(source=source, insight_type=InsightType.NARRATIVE,
                 severity=InsightSeverity.INFO, message=text[:200])
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-STEP ANALYTICAL REASONING
# ─────────────────────────────────────────────────────────────────────────────

def run_analytical_chain(
    experiment_name: str,
    db:  Any,
    llm: Any = None,
    bus: Any = None,
    session_id: str = "default",
    depth: int = 3,
) -> Dict:
    state = get_cognitive_state(session_id)
    state.experiment_name = experiment_name
    chain_results: Dict = {}

    print(f"\n{'='*72}")
    print(f"  ANALYTICAL CHAIN — {experiment_name}")
    print(f"  Running {depth} analysis stages")
    print(f"{'='*72}")

    # Stage 1: Experiment analysis
    try:
        from continum.experimentation.post_analysis.analysis import run_experiment_analysis
        ea = run_experiment_analysis(llm=llm, db=db,
                                      experiment_name=experiment_name,
                                      session_id=session_id)
        chain_results["experiment_analysis"] = ea
        post_process_module_result("experiment_analysis", ea, db, llm, bus, session_id)
    except Exception as e:
        logger.warning("Chain stage 1 failed: %s", e)
        chain_results["experiment_analysis"] = {"error": str(e)}

    if depth < 2:
        return chain_results

    # Stage 2: Causal
    try:
        from continum.experimentation.post_analysis.causal import run_causal_analysis_full
        ca = run_causal_analysis_full(db=db, llm=llm,
                                       experiment_name=experiment_name,
                                       method="did",
                                       session_id=session_id)
        chain_results["causal_analysis_full"] = ca
        post_process_module_result("causal_analysis_full", ca, db, llm, bus, session_id)
    except Exception as e:
        logger.warning("Chain stage 2 failed: %s", e)
        chain_results["causal_analysis_full"] = {"error": str(e)}

    if depth < 3:
        return chain_results

    # Stage 3: ROI
    try:
        from continum.experimentation.post_analysis.analysis import run_roi_tracker
        roi = run_roi_tracker(llm=llm, db=db, experiment_name=experiment_name,
                               session_id=session_id)
        chain_results["roi_tracker"] = roi
        post_process_module_result("roi_tracker", roi, db, llm, bus, session_id)
    except Exception as e:
        logger.warning("Chain stage 3 (ROI) failed: %s", e)
        chain_results["roi_tracker"] = {"error": str(e)}

    # Stage 4: Uplift
    try:
        from continum.experimentation.deployment import run_uplift_modeller
        uplift = run_uplift_modeller(llm=llm, db=db, experiment_name=experiment_name,
                                      session_id=session_id)
        chain_results["uplift_modeller"] = uplift
        post_process_module_result("uplift_modeller", uplift, db, llm, bus, session_id)
    except Exception as e:
        logger.warning("Chain stage 4 (uplift) failed: %s", e)
        chain_results["uplift_modeller"] = {"error": str(e)}

    # Stage 5: Decision
    try:
        from continum.experimentation.deployment import run_decision_engine
        dec = run_decision_engine(
            llm=llm, db=db, experiment_name=experiment_name,
            prev_result=chain_results.get("experiment_analysis", {}),
            session_id=session_id,
        )
        chain_results["decision_engine"] = dec
        post_process_module_result("decision_engine", dec, db, llm, bus, session_id)
    except Exception as e:
        logger.warning("Chain stage 5 (decision) failed: %s", e)
        chain_results["decision_engine"] = {"error": str(e)}

    # ── Final cross-module synthesis ───────────────────────────────────────────
    if llm is not None:
        final_synthesis = _cross_module_synthesis(state, llm)
        if final_synthesis:
            chain_results["cross_synthesis"] = final_synthesis
            print(f"\n  CROSS-MODULE SYNTHESIS\n{'─'*72}")
            print(f"  {final_synthesis}")

    return chain_results


__all__ = [
    "CognitiveState",
    "get_cognitive_state",
    "post_process_module_result",
    "run_analytical_chain",
]
