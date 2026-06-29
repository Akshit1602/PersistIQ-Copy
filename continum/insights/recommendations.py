from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("continum.insights.recommendations")


class RecommendationEngine:

    def __init__(self, session=None, bus=None, memory=None):
        self.session = session
        self.bus     = bus
        self.memory  = memory

    def run(self, after_module: Optional[str] = None) -> int:
        count = 0

        count += self._check_experiment_state()
        count += self._check_sample_ratio()
        count += self._check_missing_phases()
        count += self._check_historical_patterns()
        count += self._check_metrics()

        return count

    def _check_experiment_state(self) -> int:
        if not self.session or not self.bus:
            return 0
        count = 0
        exp   = self.session.active_experiment

        if not exp:
            self.bus.recommend(
                "recommendations",
                "Select an experiment to begin analysis",
                detail="Run any causal module after selecting an experiment",
            )
            count += 1
        elif not self.session.last_run("experiment_analysis"):
            self.bus.recommend(
                "recommendations",
                f"Run A/B readout for experiment '{exp}'",
                detail="experiment_analysis gives the full primary + segment + causal picture",
            )
            count += 1

        return count

    def _check_sample_ratio(self) -> int:
        if not self.session or not self.bus:
            return 0

        result = self.session.get("experiment_result")
        if result is None:
            return 0

        try:
            srm = getattr(result, "srm_detected", None)
            if srm is None and isinstance(result, dict):
                r = result.get("result")
                srm = getattr(r, "srm_detected", False) if r else False

            if srm:
                srm_p = getattr(result, "srm_p_value", None) or \
                        getattr(getattr(result, "result", None), "srm_p_value", None)
                self.bus.warn(
                    "recommendations",
                    "Sample Ratio Mismatch (SRM) detected — results should NOT be shipped",
                    detail=f"p={srm_p:.4f}  Investigate assignment mechanism before drawing conclusions" if srm_p else "",
                )
                self.bus.recommend(
                    "recommendations",
                    "Investigate SRM: check randomisation and assignment logic",
                    detail="SRM invalidates statistical guarantees. Do not ship based on this result.",
                )
                return 2
        except Exception:
            pass
        return 0

    def _check_missing_phases(self) -> int:
        if not self.session or not self.bus:
            return 0
        count = 0
        history_modules = {r.module for r in self.session.execution_history}

        # If analysis done but no causal analysis
        if "experiment_analysis" in history_modules and "causal_analysis" not in history_modules:
            self.bus.recommend(
                "recommendations",
                "Run causal analysis to validate the A/B findings",
                detail="7-method causal menu: DiD, ITS, PSM, RDD, SC, ARIMA, BSTS",
            )
            count += 1

        # If causal done but no learnings stored
        if ("causal_analysis" in history_modules or "experiment_analysis" in history_modules) \
                and "learnings_repository" not in history_modules:
            self.bus.recommend(
                "recommendations",
                "Store findings to Learnings Repository",
                detail="Build organisational experimentation memory for future reference",
            )
            count += 1

        # If analysis done but no segment check for Simpson's paradox
        if "experiment_analysis" in history_modules and "simpsons_paradox" not in history_modules:
            self.bus.recommend(
                "recommendations",
                "Run Simpson's Paradox Detector on segment findings",
                detail="Check if segment-level effects contradict the overall direction",
            )
            count += 1

        return count

    def _check_historical_patterns(self) -> int:
        if not self.session or not self.bus or not self.memory:
            return 0
        count = 0
        exp = self.session.active_experiment
        if not exp:
            return 0

        try:
            similar = self.memory.search_similar(exp, limit=2)
            if similar:
                names = [s["experiment_name"] for s in similar]
                self.bus.emit(
                    "recommendations",
                    f"Similar past experiment found: '{names[0]}'",
                    insight_type="recommendation",
                    severity="info",
                    detail=f"Review learnings from {', '.join(names)} before drawing conclusions",
                )
                count += 1

            # Check if this metric has a history of significance
            metrics = self.memory.get_successful_metrics(limit=3)
            if metrics and self.session.active_metrics:
                active = set(m.lower() for m in self.session.active_metrics)
                for m in metrics:
                    if m["metric_name"].lower() in active:
                        self.bus.suggest_kpi(
                            "recommendations",
                            f"'{m['metric_name']}' has {m['sig_rate']:.0%} significance rate in past experiments",
                            metric=m["metric_name"],
                        )
                        count += 1
                        break
        except Exception as e:
            logger.debug("Historical pattern check failed: %s", e)

        return count

    def _check_metrics(self) -> int:
        if not self.session or not self.bus:
            return 0
        if not self.session.active_metrics:
            self.bus.suggest_kpi(
                "recommendations",
                "Suggested KPI: Inquiry-to-Order Rate (IOR)",
                metric="inquiry_order_rate",
                detail="IOR is the primary conversion metric for most experiments in this dataset",
            )
            self.bus.suggest_kpi(
                "recommendations",
                "Suggested guardrail: Latency (p95 response time)",
                metric="p95_latency",
                detail="Prevent regressions in user experience during experimentation",
            )
            return 2
        return 0


def auto_recommend(session=None, bus=None, memory=None, after_module: Optional[str] = None) -> int:
    engine = RecommendationEngine(session=session, bus=bus, memory=memory)
    return engine.run(after_module=after_module)


__all__ = [
    "RecommendationEngine",
    "auto_recommend",
]
