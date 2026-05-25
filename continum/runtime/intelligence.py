from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, List, Optional

logger = logging.getLogger("continum.runtime.intelligence")


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHT DATA CLASS
# ─────────────────────────────────────────────────────────────────────────────

class InsightType(str, Enum):
    KPI_SUGGESTION   = "kpi_suggestion"
    WARNING          = "warning"
    RECOMMENDATION   = "recommendation"
    ANOMALY          = "anomaly"
    NARRATIVE        = "narrative"
    GUARDRAIL        = "guardrail"
    SEGMENT          = "segment"
    CAUSAL           = "causal"
    NEXT_STEP        = "next_step"
    INFO             = "info"


class InsightSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING  = "warning"
    INFO     = "info"
    SUCCESS  = "success"


_SEVERITY_ICONS = {
    InsightSeverity.CRITICAL: "🚨",
    InsightSeverity.WARNING:  "⚠️ ",
    InsightSeverity.INFO:     "💡",
    InsightSeverity.SUCCESS:  "✅",
}

_TYPE_ICONS = {
    InsightType.KPI_SUGGESTION:  "📊",
    InsightType.WARNING:         "⚠️ ",
    InsightType.RECOMMENDATION:  "💡",
    InsightType.ANOMALY:         "🔍",
    InsightType.NARRATIVE:       "📝",
    InsightType.GUARDRAIL:       "🛡️ ",
    InsightType.SEGMENT:         "🔀",
    InsightType.CAUSAL:          "🔗",
    InsightType.NEXT_STEP:       "▶️ ",
    InsightType.INFO:            "ℹ️ ",
}


@dataclass
class Insight:
    source_module: str
    insight_type:  InsightType
    severity:      InsightSeverity
    message:       str
    detail:        str         = ""
    metric:        str         = ""
    experiment_id: str         = ""
    metadata:      dict        = field(default_factory=dict)
    created_at:    str         = field(default_factory=lambda: datetime.utcnow().isoformat())
    dismissed:     bool        = False

    @property
    def icon(self) -> str:
        return _SEVERITY_ICONS.get(self.severity, "ℹ️ ")

    @property
    def type_icon(self) -> str:
        return _TYPE_ICONS.get(self.insight_type, "")

    def one_liner(self) -> str:
        return f"{self.icon} [{self.source_module}] {self.message}"

    def full_text(self) -> str:
        lines = [f"{self.icon} {self.message}"]
        if self.detail:
            lines.append(f"   {self.detail}")
        if self.metric:
            lines.append(f"   Metric: {self.metric}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHT BUS — global pub/sub
# ─────────────────────────────────────────────────────────────────────────────

class InsightBus:

    def __init__(self, max_insights: int = 200):
        self._insights:    List[Insight]                  = []
        self._subscribers: List[Callable[[Insight], None]] = []
        self._lock:        threading.Lock                  = threading.Lock()
        self._max:         int                             = max_insights

    # ── Publishing ─────────────────────────────────────────────────────────────

    def publish(self, insight: Insight) -> None:
        with self._lock:
            self._insights.append(insight)
            if len(self._insights) > self._max:
                self._insights = self._insights[-self._max:]
        for sub in self._subscribers:
            try:
                sub(insight)
            except Exception:
                pass
        logger.debug("Insight published: [%s] %s", insight.source_module, insight.message[:60])

    def emit(
        self,
        source_module: str,
        message: str,
        insight_type: InsightType = InsightType.INFO,
        severity: InsightSeverity = InsightSeverity.INFO,
        detail: str = "",
        metric: str = "",
        experiment_id: str = "",
        **metadata,
    ) -> Insight:
        ins = Insight(
            source_module=source_module,
            insight_type=insight_type,
            severity=severity,
            message=message,
            detail=detail,
            metric=metric,
            experiment_id=experiment_id,
            metadata=metadata,
        )
        self.publish(ins)
        return ins

    # ── Convenience emit shortcuts ─────────────────────────────────────────────

    def warn(self, source: str, message: str, detail: str = "", **kw) -> Insight:
        return self.emit(source, message, InsightType.WARNING, InsightSeverity.WARNING, detail=detail, **kw)

    def critical(self, source: str, message: str, detail: str = "", **kw) -> Insight:
        return self.emit(source, message, InsightType.WARNING, InsightSeverity.CRITICAL, detail=detail, **kw)

    def recommend(self, source: str, message: str, detail: str = "", **kw) -> Insight:
        return self.emit(source, message, InsightType.RECOMMENDATION, InsightSeverity.INFO, detail=detail, **kw)

    def suggest_kpi(self, source: str, message: str, metric: str = "", **kw) -> Insight:
        return self.emit(source, message, InsightType.KPI_SUGGESTION, InsightSeverity.INFO, metric=metric, **kw)

    def anomaly(self, source: str, message: str, detail: str = "", **kw) -> Insight:
        return self.emit(source, message, InsightType.ANOMALY, InsightSeverity.WARNING, detail=detail, **kw)

    def next_step(self, source: str, message: str, **kw) -> Insight:
        return self.emit(source, message, InsightType.NEXT_STEP, InsightSeverity.INFO, **kw)

    def success(self, source: str, message: str, **kw) -> Insight:
        return self.emit(source, message, InsightType.INFO, InsightSeverity.SUCCESS, **kw)

    # ── Querying ───────────────────────────────────────────────────────────────

    def all(self) -> List[Insight]:
        with self._lock:
            return [i for i in self._insights if not i.dismissed]

    def by_type(self, *types: InsightType) -> List[Insight]:
        return [i for i in self.all() if i.insight_type in types]

    def by_severity(self, *severities: InsightSeverity) -> List[Insight]:
        return [i for i in self.all() if i.severity in severities]

    def by_module(self, module: str) -> List[Insight]:
        return [i for i in self.all() if i.source_module == module]

    def warnings(self) -> List[Insight]:
        return self.by_severity(InsightSeverity.WARNING, InsightSeverity.CRITICAL)

    def recommendations(self) -> List[Insight]:
        return self.by_type(InsightType.RECOMMENDATION, InsightType.NEXT_STEP)

    def kpi_suggestions(self) -> List[Insight]:
        return self.by_type(InsightType.KPI_SUGGESTION)

    def recent(self, n: int = 10) -> List[Insight]:
        return self.all()[-n:]

    def clear(self) -> None:
        with self._lock:
            self._insights = []

    def subscribe(self, fn: Callable[[Insight], None]) -> None:
        self._subscribers.append(fn)

    # ── Display ────────────────────────────────────────────────────────────────

    def render_panel(self, max_items: int = 15, width: int = 72) -> str:
        insights = self.all()[-max_items:]
        if not insights:
            return ""

        inner_w = width - 4
        lines   = [f"╔{'═' * (width - 2)}╗"]
        title   = " INSIGHTS "
        pad_l   = (width - 2 - len(title)) // 2
        pad_r   = (width - 2 - len(title)) - pad_l
        lines.append(f"║{'═' * pad_l}{title}{'═' * pad_r}║")

        for ins in insights:
            text = f"{ins.type_icon} {ins.message}"
            # Truncate if needed
            if len(text) > inner_w:
                text = text[:inner_w - 1] + "…"
            padding = inner_w - len(text)
            lines.append(f"║  {text}{' ' * padding}  ║")

        lines.append(f"╚{'═' * (width - 2)}╝")
        return "\n".join(lines)

    def render_summary(self) -> str:
        warnings = len(self.warnings())
        recs     = len(self.recommendations())
        kpis     = len(self.kpi_suggestions())
        total    = len(self.all())
        if total == 0:
            return ""
        parts = []
        if warnings:
            parts.append(f"⚠️  {warnings} warning{'s' if warnings > 1 else ''}")
        if recs:
            parts.append(f"💡 {recs} recommendation{'s' if recs > 1 else ''}")
        if kpis:
            parts.append(f"📊 {kpis} KPI suggestion{'s' if kpis > 1 else ''}")
        return "  " + " · ".join(parts) if parts else ""


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

_BUS: Optional[InsightBus] = None


def get_bus() -> InsightBus:
    global _BUS
    if _BUS is None:
        _BUS = InsightBus()
    return _BUS


def reset_bus() -> None:
    global _BUS
    _BUS = InsightBus()


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW TRANSITION RECOMMENDATIONS
# ─────────────────────────────────────────────────────────────────────────────

# Maps phase/module → what the system should recommend next
WORKFLOW_CHAIN: dict = {
    "schema_discovery":    [("power_calculator",   "Run power analysis on discovered schema",       2),
                            ("data_validation",    "Validate data quality before experimenting",    1)],
    "data_validation":     [("dimension_setup",    "Auto-detect segments and dimensions",           1),
                            ("opportunity_sizing", "Quantify the revenue opportunity",              2)],
    "dimension_setup":     [("opportunity_sizing", "Size the revenue opportunity",                  1)],
    "opportunity_sizing":  [("power_calculator",   "Calculate sample size for this opportunity",    1),
                            ("brief_generator",    "Generate experiment brief",                     2)],
    "power_calculator":    [("brief_generator",    "Generate full experiment brief",                1),
                            ("audience_selection", "Select and score target audience",              2)],
    "brief_generator":     [("audience_selection", "Define audience for this experiment",           1),
                            ("metrics_and_tracking","Build KPI & tracking plan",                   2)],
    "audience_selection":  [("health_monitor",     "Monitor experiment health once launched",       2),
                            ("sequential_testing", "Set up sequential testing for early stopping",  1)],
    "metrics_and_tracking":[("health_monitor",     "Monitor KPIs in real time",                    1)],
    "health_monitor":      [("experiment_analysis","Run full post-experiment readout",              1),
                            ("sequential_testing", "Check if experiment can stop early",           2)],
    "sequential_testing":  [("experiment_analysis","Analyse the concluded experiment",             1)],
    "experiment_analysis": [("causal_analysis",    "Deep-dive causal analysis",                    1),
                            ("simpsons_paradox",   "Check for Simpson's paradox in segments",      2),
                            ("roi_tracker",        "Track incremental ROI post-ship",              3)],
    "causal_analysis":     [("uplift_modeller",    "Estimate individual-level causal effects",     1),
                            ("learnings_repository","Store insights to the learnings repository",  2)],
    "simpsons_paradox":    [("causal_analysis",    "Run causal analysis to explain the paradox",   1)],
    "roi_tracker":         [("learnings_repository","Save ROI findings for future experiments",    1)],
    "uplift_modeller":     [("decision_engine",    "Optimise targeting using uplift scores",       1)],
}


def publish_next_steps(module: str, bus: Optional[InsightBus] = None) -> None:
    target_bus = bus or get_bus()
    if target_bus is None:
        return

    try:
        from continum.modules.intelligence.synthesis import (
            run_next_step_generation, _PHASE_TRANSITIONS,
        )
        steps = _PHASE_TRANSITIONS.get(module, [])
        for step in steps[:3]:
            target_bus.next_step(
                source=module,
                message=f"Suggested: run {step['module']}",
                detail=step.get("reason", ""),
            )
        return
    except ImportError:
        pass

    # Static fallback (no extra imports required)
    _STATIC_NEXT: dict = {
        "power_calculator":    ("opportunity_sizing",   "Size the revenue opportunity"),
        "opportunity_sizing":  ("brief_generator",      "Generate experiment brief"),
        "brief_generator":     ("metrics_and_tracking", "Define KPIs and tracking plan"),
        "metrics_and_tracking":("audience_selection",   "Select experiment audience"),
        "health_monitor":      ("sequential_testing",   "Check always-valid p-values"),
        "sequential_testing":  ("experiment_analysis",  "Run full post-experiment analysis"),
        "experiment_analysis": ("causal_analysis",      "Strengthen causal claim with DiD/PSM"),
        "causal_analysis":     ("roi_tracker",          "Quantify post-ship incremental GMV"),
        "roi_tracker":         ("uplift_modeller",      "Model per-user treatment effect"),
        "simpsons_paradox":    ("causal_analysis",      "Re-run causal analysis stratified by segment"),
    }
    if module in _STATIC_NEXT:
        next_mod, reason = _STATIC_NEXT[module]
        target_bus.next_step(source=module, message=f"Suggested: run {next_mod}", detail=reason)

