"""MatchView tool-calling layer (detect → confirm → execute).

When a user's request maps to a MatchView application module, this layer:

    1. detects the intent  ............ ``detect_tool``
    2. asks the user to confirm  ...... ``confirmation_message``
    3. on confirm, executes the real
       underlying capability  ......... ``execute_tool``

Execution either defers to the AskData NL->SQL engine (data look-ups, chartable)
or invokes a real analysis / deployment module from ``continum.ExpSuite.registry``.
Each tool is named with the EXACT module label the user sees on its dashboard card
and carries its lifecycle ``phase``. Module execution is best-effort: if a module
needs more setup than the chat can supply, we fall back to a data-grounded answer.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("continum.orchestration.matchview")

# Tool "kind" — drives how the result is fetched and whether a deploy warning fires.
KIND_DATA = "data"  # NL -> SQL look-up via the AskData engine (chartable)
KIND_ANALYSIS = "analysis"  # a real registry analysis module
KIND_DEPLOY = "deploy"  # a go-live / activation action (always warned)


@dataclass
class MatchViewTool:
    """A user-facing MatchView module mapped onto a real Continum capability."""

    key: str
    module_name: str
    kind: str  # KIND_DATA | KIND_ANALYSIS | KIND_DEPLOY
    target: str  # registry module key, or "askdata"
    triggers: List[str]
    phase: str = ""
    patterns: List[str] = field(default_factory=list)
    action_verb: str = "answer this"
    next_steps: List[str] = field(default_factory=list)
    description: str = ""

    def matches(self, q: str) -> bool:
        ql = q.lower()
        if any(t in ql for t in self.triggers):
            return True
        return any(re.search(p, ql) for p in self.patterns)


# Ordered most-specific-first: action/deploy intents win over generic look-ups.
MATCHVIEW_TOOLS: List[MatchViewTool] = [
    MatchViewTool(
        key="deploy",
        module_name="Uplift Modeller",
        phase="Deployment",
        kind=KIND_DEPLOY,
        target="uplift_modeller",
        triggers=[
            "launch",
            "deploy",
            "activate",
            "go live",
            "golive",
            "roll out",
            "rollout",
            "ship it",
            "send the campaign",
            "send this campaign",
            "send campaign",
            "turn on",
            "publish",
            "make it live",
        ],
        action_verb="take this action",
        next_steps=[
            "Show the uplift scores by segment",
            "Run the decision engine to optimise targeting",
        ],
        description="Activate / roll out (uplift modelling + budget-constrained targeting).",
    ),
    MatchViewTool(
        key="audience",
        module_name="Audience Selection",
        phase="Planning",
        kind=KIND_ANALYSIS,
        target="audience_selection",
        triggers=[
            "lead list",
            "lead-list",
            "leads",
            "audience",
            "who should i target",
            "who to target",
            "targeting",
            "propensity",
            "build a list",
        ],
        action_verb="take this action",
        next_steps=[
            "Estimate the opportunity size for this audience",
            "Would you like to launch a sequence to this audience?",
        ],
        description="Propensity-scored audience / lead-list selection.",
    ),
    MatchViewTool(
        key="campaign_readout",
        module_name="A/B Readout",
        phase="Analysis & Readout",
        kind=KIND_ANALYSIS,
        target="experiment_analysis",
        triggers=[
            "campaign",
            "sequence result",
            "experiment result",
            "experiment readout",
            "read out",
            "a/b readout",
            "ab readout",
            "run the readout",
            "how did the experiment",
            "how is the experiment",
            "did it win",
            "winner",
            "results of",
            "ab test",
            "a/b test",
        ],
        action_verb="answer this",
        next_steps=["Why did it win or lose? (causal analysis)", "Track the ROI of this campaign"],
        description="Campaign / experiment A/B readout pipeline.",
    ),
    MatchViewTool(
        key="causal",
        module_name="Causal Analysis",
        phase="Analysis & Readout",
        kind=KIND_ANALYSIS,
        target="causal_analysis",
        triggers=[
            "why did",
            "root cause",
            "what caused",
            "attribution",
            "causal",
            "explain why",
            "what drove",
        ],
        action_verb="answer this",
        next_steps=["Check for Simpson's paradox across segments", "Summarise the key learnings"],
        description="Causal attribution analysis (DiD, PSM, ITS, ...).",
    ),
    MatchViewTool(
        key="health",
        module_name="Health Monitor",
        phase="Live Monitoring",
        kind=KIND_ANALYSIS,
        target="health_monitor",
        triggers=[
            "health",
            "healthy",
            "is it healthy",
            "srm",
            "guardrail",
            "sample ratio",
            "monitor",
            "is the experiment ok",
            "anything wrong",
        ],
        action_verb="answer this",
        next_steps=[
            "Run sequential testing for an always-valid p-value",
            "Show the guardrail breakdown",
        ],
        description="SRM, guardrails, IOR trajectory and ETA-to-significance.",
    ),
    MatchViewTool(
        key="email_analytics",
        module_name="Email Analytics",
        kind=KIND_DATA,
        target="askdata",
        triggers=[
            "email analytics",
            "open rate",
            "click rate",
            "reply rate",
            "deliverability",
            "bounce rate",
            "performance by",
            "metrics by",
            "conversion by",
            "breakdown by",
            "rate by",
        ],
        action_verb="answer this",
        next_steps=["Break this down by another segment", "Compare against the previous period"],
        description="Campaign / email performance analytics over the dataset.",
    ),
]

# How-to / informational phrasing — these belong to the Guide engine, not an action.
_HOWTO_MARKERS = (
    "how do i",
    "how to",
    "how does",
    "how can i",
    "what is",
    "what are",
    "what can you",
    "explain the",
    "guide",
    "tutorial",
    "where do i",
    "which module",
    "what module",
    "getting started",
)


def detect_tool(question: str, ui_context: Optional[dict] = None) -> Optional[MatchViewTool]:
    """Return the MatchView tool a question maps to, or None.

    How-to / "about the tool" questions are intentionally *not* intercepted —
    those should be answered by the Guide engine, not by taking an action.
    """
    q = (question or "").strip().lower()
    if not q:
        return None
    if any(m in q for m in _HOWTO_MARKERS):
        return None
    for tool in MATCHVIEW_TOOLS:
        if tool.matches(q):
            return tool
    return None


def get_tool(key: str) -> Optional[MatchViewTool]:
    for tool in MATCHVIEW_TOOLS:
        if tool.key == key:
            return tool
    return None


def confirmation_message(tool: MatchViewTool) -> str:
    """The mandatory 'would you like to use the module?' prompt (with a one-line
    description of what the module will do)."""
    what = (tool.description or "").strip().rstrip(".")
    what_line = f" It will **{what.lower()}**." if what else ""
    phase_line = f" (in the **{tool.phase}** phase)" if tool.phase else ""
    return (
        f"That looks like a job for the **{tool.module_name}** module{phase_line}."
        f"{what_line} Would you like to run **{tool.module_name}** to {tool.action_verb}?"
    )


def deploy_warning(tool: MatchViewTool) -> str:
    """Prominent warning shown for any deploy / go-live action."""
    return (
        f"⚠️ **Deploy / go-live warning** — This moves **{tool.module_name}** from an "
        "experimentation / draft state into a **LIVE** environment. Live actions affect "
        "real audiences, real sends, and real budget, and cannot be undone from this chat. "
        "Confirm your guardrails and approvals are in place before continuing."
    )


def execute_tool(
    app, tool: MatchViewTool, question: str, ui_context: Optional[dict] = None
) -> Dict[str, Any]:
    """Run the capability behind a confirmed tool.

    Returns a dict shaped like the AskData engine's output so the endpoint and
    Copilot pane can render it uniformly.
    """
    ui_context = ui_context or {}

    # Data look-ups go straight to the reliable NL->SQL engine (chartable result).
    if tool.kind == KIND_DATA or tool.target == "askdata":
        return _run_askdata(app, question, ui_context)

    # Analysis / deploy → invoke the real registry module, best-effort.
    try:
        from continum.ExpSuite.registry import run_module

        exp = (
            ui_context.get("active_experiment")
            or getattr(getattr(app, "ses", None), "active_experiment", None)
            or ""
        )
        kwargs: Dict[str, Any] = {}
        if tool.target == "experiment_analysis":
            kwargs = {"experiment_name": exp, "experiment_id": exp}
        result = run_module(
            tool.target,
            state=getattr(app, "state", None),
            llm=getattr(app, "llm", None),
            db=getattr(app, "db", None),
            **kwargs,
        )
        return {
            "response": _summarise_result(result, tool),
            "sql": None,
            "table": [],
            "columns": [],
            "visualizations": [],
            "error": None,
        }
    except Exception as e:  # noqa: BLE001 — never surface a stack trace to chat
        logger.warning(
            "Tool %r module %r failed (%s) — falling back to AskData", tool.key, tool.target, e
        )
        out = _run_askdata(app, question, ui_context)
        note = (
            f"I tried the **{tool.module_name}** module, but it needs an active "
            "experiment / more setup in this session — so here's a data-grounded "
            "answer instead:\n\n"
        )
        out["response"] = note + (out.get("response") or "")
        return out


def _run_askdata(app, question: str, ui_context: dict) -> Dict[str, Any]:
    from continum.orchestration import get_askdata_engine

    d = get_askdata_engine(app).ask(question, ui_context=ui_context)
    return {
        "response": d.get("response", ""),
        "sql": d.get("sql"),
        "table": d.get("table", []),
        "columns": d.get("columns", []),
        "visualizations": d.get("visualizations", []) or [],
        "error": d.get("error"),
    }


def _summarise_result(result: Any, tool: MatchViewTool) -> str:
    """Turn a heterogeneous module result into a readable chat message."""
    if result is None:
        return f"The **{tool.module_name}** module ran but returned no result."
    try:
        delta = getattr(result, "primary_delta", None)
        verdict = getattr(result, "verdict", None)
        if delta is not None and verdict is not None:
            sig = "significant ✅" if getattr(delta, "is_significant", False) else "not significant"
            v = getattr(verdict, "value", verdict)
            return (
                f"**{tool.module_name}** — {v}: Δ={delta.delta_pp:+.3f}pp, "
                f"p={delta.p_value:.4f} ({sig})."
            )
        for attr in ("narrative", "summary", "message"):
            v = getattr(result, attr, None)
            if isinstance(v, str) and v.strip():
                return v.strip()
        if isinstance(result, dict):
            if result.get("error"):
                return f"The **{tool.module_name}** module reported: {result['error']}"
            for k in ("narrative", "summary", "message", "verdict"):
                v = result.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            bits = [
                f"- **{k}**: {v}"
                for k, v in result.items()
                if isinstance(v, (str, int, float, bool))
            ][:6]
            if bits:
                return f"**{tool.module_name}** results:\n" + "\n".join(bits)
        return f"**{tool.module_name}** completed.\n\n" + str(result)[:300]
    except Exception:  # noqa: BLE001
        return f"**{tool.module_name}** completed."


# ===== relocated from the former runtime.shell.executor (used by userui) =====
def _summarise(result: Any, module_key: str) -> str:
    if result is None:
        return ""
    try:
        if hasattr(result, "verdict") and hasattr(result, "primary_delta"):
            d = result.primary_delta
            return (
                f"Δ={d.delta_pp:+.3f}pp  p={d.p_value:.4f}  "
                f"{'✅' if d.is_significant else '—'}  {result.verdict.value}"
            )
        if isinstance(result, dict):
            r = result.get("result")
            if r and hasattr(r, "verdict"):
                d = r.primary_delta
                return f"Δ={d.delta_pp:+.3f}pp  p={d.p_value:.4f}  {r.verdict.value}"
            if "error" in result:
                return f"Error: {result['error']}"
            return str(list(result.keys()))[:60]
        return str(result)[:60]
    except Exception:
        return ""


__all__ = [
    "MatchViewTool",
    "MATCHVIEW_TOOLS",
    "detect_tool",
    "get_tool",
    "confirmation_message",
    "deploy_warning",
    "execute_tool",
    "_summarise",
    "_summarise_result",
    "KIND_DATA",
    "KIND_ANALYSIS",
    "KIND_DEPLOY",
]
