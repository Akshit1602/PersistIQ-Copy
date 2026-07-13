"""
Guided experimentation flow for the Continum Copilot (MVP2).

Where ``tools.py`` is *reactive* — a single question is mapped to one module,
confirmed, and run — this module is *proactive*. It treats every MatchView
module as a tool and walks the user through the experimentation lifecycle:

    1. locate   — figure out where the user is, from what they've already run
    2. suggest  — propose the next logical step(s) as pickable options
    3. fill      — once a step is picked, ask one question per input field
                   (with smart defaults), collecting the module's kwargs
    4. confirm  — show the gathered inputs and hand off to execution

The engine is deliberately *pure* and *deterministic*: it holds no app/UI
imports and works with or without an LLM loaded. The Flask endpoint
(``/api/copilot/flow``) injects the per-module field schema (the same
``_get_module_config`` the config form uses) and the live session, then renders
the returned text + chips in the chat pane. Conversation state is a tiny dict
(``stage``/``module_key``/``idx``/``collected``) round-tripped to the client, so
the server stays stateless across turns.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("continum.askdata.flow")


# ─────────────────────────────────────────────────────────────────────────────
# LIFECYCLE PLAN
# The five user-facing phases (README) and the primary module ("tool") in each,
# in the order a guided run would naturally take them. We locate the user by
# module *membership* here — not by the dispatcher's phase tag — so the guided
# narrative stays stable even as modules are re-registered across phases.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PhaseStep:
    key: str
    label: str
    blurb: str
    modules: List[str]


PHASE_PLAN: List[PhaseStep] = [
    PhaseStep(
        "discovery",
        "Discovery",
        "connect data, validate it, and map the schema",
        ["schema_discovery", "data_validation", "dimension_setup"],
    ),
    PhaseStep(
        "planning",
        "Planning",
        "size the opportunity, check power, define metrics and audience",
        [
            "opportunity_sizing",
            "power_calculator",
            "metrics_and_tracking",
            "audience_selection",
            "brief_generator",
        ],
    ),
    PhaseStep(
        "monitoring",
        "Live Monitoring",
        "watch health and run sequential tests while the experiment is live",
        ["health_monitor", "sequential_testing"],
    ),
    PhaseStep(
        "analysis",
        "Analysis & Readout",
        "read out the result, attribute the cause, and store the learning",
        [
            "experiment_analysis",
            "causal_analysis",
            "simpsons_paradox",
            "roi_tracker",
            "learnings_repository",
        ],
    ),
    PhaseStep(
        "deployment",
        "Deployment",
        "model individual uplift and decide the rollout",
        ["uplift_modeller", "decision_engine"],
    ),
]


# Friendly names for chips / prose. Falls back to a humanised key.
MODULE_LABELS: Dict[str, str] = {
    "schema_discovery": "Schema Discovery",
    "data_validation": "Data Validation",
    "dimension_setup": "Dimension Setup",
    "opportunity_sizing": "Opportunity Sizing",
    "power_calculator": "Power Calculator",
    "metrics_and_tracking": "KPI & Tracking Plan",
    "audience_selection": "Audience Selection",
    "brief_generator": "Experiment Brief",
    "health_monitor": "Health Monitor",
    "sequential_testing": "Sequential Testing",
    "experiment_analysis": "A/B Readout",
    "causal_analysis": "Causal Analysis",
    "simpsons_paradox": "Simpson's Paradox Check",
    "roi_tracker": "ROI Tracker",
    "learnings_repository": "Learnings Repository",
    "uplift_modeller": "Uplift Modeller",
    "decision_engine": "Decision Engine",
}

# Module → its phase index in PHASE_PLAN, built once.
_MODULE_PHASE: Dict[str, int] = {m: i for i, step in enumerate(PHASE_PLAN) for m in step.modules}


def module_label(key: str) -> str:
    return MODULE_LABELS.get(key, key.replace("_", " ").title())


# ─────────────────────────────────────────────────────────────────────────────
# TRIGGERS — phrases that should start / restart the guided flow
# ─────────────────────────────────────────────────────────────────────────────

_TRIGGERS = (
    "where am i",
    "what's next",
    "whats next",
    "what next",
    "next step",
    "what should i do",
    "what do i do",
    "guide me",
    "walk me through",
    "help me run",
    "start an experiment",
    "run an experiment",
    "where do i start",
    "what step",
    "guide",
    "__next__",
    "__start__",
)


def is_flow_trigger(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return any(k in t for k in _TRIGGERS)


def is_restart(text: str) -> bool:
    """A flow turn that should reset to the overview/choosing stage."""
    t = (text or "").strip().lower()
    return (not t) or t in ("__next__", "__start__") or is_flow_trigger(t)


def is_yes(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(re.match(r"^(y|yes|yep|yeah|yup|sure|ok|okay|go|run|do it|confirm|proceed)\b", t))


def is_no(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(re.match(r"^(n|no|nope|cancel|stop|don'?t|abort|never)\b", t))


def _is_default_token(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in ("", "ok", "okay", "default", "use default", "skip", "yes", "y", "next", "accept")


# ─────────────────────────────────────────────────────────────────────────────
# LOCATE — "where are you in the process?"
# ─────────────────────────────────────────────────────────────────────────────


def _ok_modules(session) -> List[str]:
    """Successfully-run module keys, in order, de-duplicated to the last run."""
    if session is None:
        return []
    seen: List[str] = []
    for rec in getattr(session, "execution_history", []) or []:
        if getattr(rec, "ok", True):
            mod = getattr(rec, "module", "")
            if mod and mod not in seen:
                seen.append(mod)
    return seen


def locate(session) -> Dict[str, Any]:
    """Summarise progress through PHASE_PLAN from the session's run history."""
    done = set(_ok_modules(session))
    done_in_plan = [m for m in done if m in _MODULE_PHASE]

    # Current phase = furthest phase reached, else Discovery (start).
    if done_in_plan:
        cur_idx = max(_MODULE_PHASE[m] for m in done_in_plan)
    else:
        cur_idx = 0

    per_phase = []
    for i, step in enumerate(PHASE_PLAN):
        ran = [m for m in step.modules if m in done]
        per_phase.append(
            {
                "key": step.key,
                "label": step.label,
                "ran": ran,
                "total": len(step.modules),
                "complete": len(ran) == len(step.modules),
            }
        )

    active_exp = getattr(session, "active_experiment", None) if session else None
    n_runs = len(getattr(session, "execution_history", []) or []) if session else 0

    if not done_in_plan:
        line = "You haven't run anything yet — let's start at **Discovery**."
    else:
        cur = PHASE_PLAN[cur_idx]
        line = (
            f"You're in **{cur.label}** "
            f"({len(per_phase[cur_idx]['ran'])}/{len(cur.modules)} steps done). "
            f"{n_runs} module run(s) so far"
            + (f", on experiment **{active_exp}**." if active_exp else ".")
        )

    return {
        "current_phase": cur_idx,
        "current_label": PHASE_PLAN[cur_idx].label,
        "per_phase": per_phase,
        "active_experiment": active_exp,
        "line": line,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SUGGEST — "what's the next step?"
# ─────────────────────────────────────────────────────────────────────────────


def suggest_next(session, limit: int = 4) -> List[Dict[str, str]]:
    """Ordered next-step suggestions: finish the current phase, then advance."""
    done = set(_ok_modules(session))
    prog = locate(session)
    cur_idx = prog["current_phase"]

    out: List[Dict[str, str]] = []
    seen: set = set()

    def _add(mod: str, reason: str):
        if mod in seen or mod in done:
            return
        seen.add(mod)
        out.append(
            {
                "module_key": mod,
                "label": module_label(mod),
                "phase": PHASE_PLAN[_MODULE_PHASE[mod]].label,
                "reason": reason,
            }
        )

    # 1) Unrun steps in the current phase.
    for m in PHASE_PLAN[cur_idx].modules:
        _add(m, f"continue {PHASE_PLAN[cur_idx].label}")
        if len(out) >= limit:
            return out

    # 2) The headline (first) step of each subsequent phase.
    for i in range(cur_idx + 1, len(PHASE_PLAN)):
        step = PHASE_PLAN[i]
        if step.modules:
            _add(step.modules[0], f"start {step.label} — {step.blurb}")
        if len(out) >= limit:
            return out

    # 3) If everything is done, offer to revisit Analysis / loop back.
    if not out:
        for m in PHASE_PLAN[3].modules[:limit]:
            seen.discard(m)  # allow re-running in the all-done case
            out.append(
                {
                    "module_key": m,
                    "label": module_label(m),
                    "phase": PHASE_PLAN[3].label,
                    "reason": "revisit analysis",
                }
            )
    return out[:limit]


def render_overview(prog: Dict[str, Any], sugg: List[Dict[str, str]]) -> str:
    """The 'where you are + what's next' message that opens the flow."""
    lines = ["🧭 **Guided experimentation**", "", prog["line"], ""]

    # Compact phase ledger.
    ledger = []
    for p in prog["per_phase"]:
        if p["complete"]:
            mark = "✅"
        elif p["ran"]:
            mark = "🔵"
        else:
            mark = "⚪"
        ledger.append(f"{mark} {p['label']} ({len(p['ran'])}/{p['total']})")
    lines.append("  ·  ".join(ledger))
    lines.append("")

    if sugg:
        lines.append("**Suggested next step** — pick one (or ask me anything):")
        for s in sugg:
            lines.append(f"  • **{s['label']}** — {s['reason']}")
    else:
        lines.append(
            "You've covered the whole lifecycle. Pick any module to re-run, "
            "or ask a data question."
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MODULE MATCHING — interpret the user's pick in the 'choosing' stage
# ─────────────────────────────────────────────────────────────────────────────


def match_module(text: str, session) -> Optional[str]:
    """Resolve a free-text / chip message to a module key, or 'askdata', or None."""
    t = (text or "").strip().lower()
    if not t:
        return None

    if any(
        k in t for k in ("ask data", "askdata", "data question", "query the data", "ask a question")
    ):
        return "askdata"

    # Exact key (chips send the key).
    if t in _MODULE_PHASE:
        return t
    cleaned = t.replace(" ", "_")
    if cleaned in _MODULE_PHASE:
        return cleaned

    # Friendly-label match (full, then substring).
    for key in _MODULE_PHASE:
        if module_label(key).lower() == t:
            return key
    best = None
    for key in _MODULE_PHASE:
        lbl = module_label(key).lower()
        if lbl in t or t in lbl:
            best = key
            break
    if best:
        return best

    # Keyword fallbacks for natural phrasing.
    kw = {
        "power": "power_calculator",
        "sample size": "power_calculator",
        "opportunity": "opportunity_sizing",
        "sizing": "opportunity_sizing",
        "brief": "brief_generator",
        "kpi": "metrics_and_tracking",
        "metric": "metrics_and_tracking",
        "tracking": "metrics_and_tracking",
        "audience": "audience_selection",
        "lead": "audience_selection",
        "health": "health_monitor",
        "srm": "health_monitor",
        "sequential": "sequential_testing",
        "msprt": "sequential_testing",
        "readout": "experiment_analysis",
        "a/b": "experiment_analysis",
        "ab test": "experiment_analysis",
        "analysis": "experiment_analysis",
        "causal": "causal_analysis",
        "attribution": "causal_analysis",
        "simpson": "simpsons_paradox",
        "roi": "roi_tracker",
        "revenue": "roi_tracker",
        "learning": "learnings_repository",
        "repository": "learnings_repository",
        "uplift": "uplift_modeller",
        "decision": "decision_engine",
        "rollout": "decision_engine",
        "discovery": "schema_discovery",
        "schema": "schema_discovery",
        "validate": "data_validation",
        "validation": "data_validation",
        "dimension": "dimension_setup",
    }
    for frag, key in kw.items():
        if frag in t:
            return key
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SLOT FILLING — ask one question per input field
# ─────────────────────────────────────────────────────────────────────────────


def _fields(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(config.get("fields") or [])


def init_slots(
    module_key: str, config: Dict[str, Any], active_experiment: str = ""
) -> Dict[str, Any]:
    """Begin a fill for ``module_key``. Pre-seeds an active experiment if the
    module needs one, so we can offer it as the default rather than asking cold.
    """
    collected: Dict[str, Any] = {}
    if active_experiment:
        for f in _fields(config):
            if f.get("type") == "experiment_select" and not collected.get(f["key"]):
                collected[f["key"]] = active_experiment
    state = {
        "stage": "filling",
        "module_key": module_key,
        "idx": 0,
        "collected": collected,
    }
    # No fields → straight to confirm (e.g. discovery modules).
    if not _fields(config):
        state["stage"] = "confirm"
    return state


def _coerce(field_spec: Dict[str, Any], text: str) -> Tuple[Any, Optional[str]]:
    """Parse a raw answer into the field's type. Returns (value, error)."""
    ftype = field_spec.get("type", "text")
    raw = (text or "").strip()

    if ftype in ("int", "float"):
        cleaned = raw.replace(",", "").replace("$", "").replace("%", "").strip()
        try:
            val = float(cleaned)
        except ValueError:
            return None, f"'{raw}' isn't a number — try a value like {field_spec.get('default')}."
        lo, hi = field_spec.get("min"), field_spec.get("max")
        if lo is not None and val < lo:
            return None, f"Value must be ≥ {lo}."
        if hi is not None and val > hi:
            return None, f"Value must be ≤ {hi}."
        return (int(val) if ftype == "int" else val), None

    if ftype in ("select", "experiment_select"):
        val = _match_option(field_spec, raw)
        if val is None:
            return None, "I didn't recognise that option — pick one of the choices below."
        return val, None

    return raw, None  # plain text


def _match_option(field_spec: Dict[str, Any], raw: str) -> Optional[str]:
    """Map a typed/clicked answer to a concrete option value."""
    t = raw.strip().lower()
    ftype = field_spec.get("type")

    if ftype == "experiment_select":
        opts = field_spec.get("options") or []  # [{name,n,variants}]
        names = [str(o.get("name", "")) for o in opts]
        for n in names:
            if n.lower() == t:
                return n
        for n in names:
            if t and (t in n.lower() or n.lower() in t):
                return n
        if t.isdigit() and 1 <= int(t) <= len(names):
            return names[int(t) - 1]
        # No experiments to match against → accept the typed name as-is.
        return raw.strip() if (not names and raw.strip()) else None

    # plain select
    options = field_spec.get("options") or []
    values = field_spec.get("option_values") or options
    for i, opt in enumerate(options):
        val = str(values[i]) if i < len(values) else str(opt)
        label = str(opt).lower()
        token = label.split("—")[0].split("-")[0].strip()  # leading "1" / "mvp"
        if t == val.lower() or t == label or t == token:
            return val
        if t and t in label:
            return val
    if t.isdigit() and 1 <= int(t) <= len(values):
        return str(values[int(t) - 1])
    return None


def record_answer(
    state: Dict[str, Any], text: str, config: Dict[str, Any]
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Apply the user's answer to the current slot and advance. On a parse
    error the state is returned unchanged with an error message to re-prompt.
    """
    fields = _fields(config)
    idx = int(state.get("idx", 0))
    if idx >= len(fields):
        state["stage"] = "confirm"
        return state, None

    f = fields[idx]
    if _is_default_token(text):
        # Accept default (skip). For experiment_select, keep any pre-seeded value.
        pre = state["collected"].get(f["key"])
        value = pre if pre not in (None, "") else f.get("default", "")
    else:
        value, err = _coerce(f, text)
        if err:
            return state, err

    state["collected"][f["key"]] = value
    state["idx"] = idx + 1
    if state["idx"] >= len(fields):
        state["stage"] = "confirm"
    return state, None


def format_question(
    state: Dict[str, Any], config: Dict[str, Any]
) -> Tuple[str, List[Dict[str, str]]]:
    """Prompt + chips for the current slot."""
    fields = _fields(config)
    idx = int(state.get("idx", 0))
    f = fields[idx]
    title = config.get("title", module_label(state["module_key"]))

    head = f"**{title}** — step {idx + 1} of {len(fields)}"
    qline = f"**{f.get('label', f['key'])}?**"
    bits = [head, "", qline]
    if f.get("help"):
        bits.append(f"_{f['help']}_")

    chips: List[Dict[str, str]] = []
    ftype = f.get("type")

    if ftype == "select":
        options = f.get("options") or []
        values = f.get("option_values") or options
        for i, opt in enumerate(options):
            val = str(values[i]) if i < len(values) else str(opt)
            chips.append({"label": str(opt), "value": val})
        bits.append("\nPick an option:")
    elif ftype == "experiment_select":
        opts = f.get("options") or []
        pre = state["collected"].get(f["key"])
        if pre:
            chips.append({"label": f"✅ Use active: {pre}", "value": "ok"})
        for o in opts[:6]:
            nm = str(o.get("name", ""))
            chips.append({"label": f"{nm} ({o.get('n','?')} rows)", "value": nm})
        if not opts and not pre:
            bits.append("\n_No experiments detected — type the experiment name._")
        else:
            bits.append("\nWhich experiment?")
    else:
        dflt = f.get("default", "")
        if dflt not in (None, ""):
            chips.append({"label": f"Use default: {dflt}", "value": "ok"})
            bits.append(f"\n_Type a value, or accept the default ({dflt})._")
        else:
            bits.append("\n_Type your answer._")

    return "\n".join(bits), chips


def format_confirm(
    state: Dict[str, Any], config: Dict[str, Any]
) -> Tuple[str, List[Dict[str, str]]]:
    """Summary of gathered inputs + run / restart / cancel chips."""
    fields = {f["key"]: f for f in _fields(config)}
    title = config.get("title", module_label(state["module_key"]))
    lines = [f"Ready to run **{title}** with:"]
    collected = run_fields(state)
    if collected:
        for k, v in collected.items():
            lbl = fields.get(k, {}).get("label", k)
            lines.append(f"  • {lbl}: **{v}**")
    else:
        lines.append("  • _(no inputs required)_")
    lines.append("\nShall I run it?")
    chips = [
        {"label": f"▶ Run {title}", "value": "run"},
        {"label": "✏️ Start over", "value": "__edit__"},
        {"label": "✖ Cancel", "value": "__cancel__"},
    ]
    return "\n".join(lines), chips


def run_fields(state: Dict[str, Any]) -> Dict[str, Any]:
    """The collected slot values to hand to /api/execute, dropping empties
    (mirrors the config form's collectFormValues)."""
    return {k: v for k, v in (state.get("collected") or {}).items() if v not in (None, "")}


__all__ = [
    "PhaseStep",
    "PHASE_PLAN",
    "MODULE_LABELS",
    "module_label",
    "is_flow_trigger",
    "is_restart",
    "is_yes",
    "is_no",
    "locate",
    "suggest_next",
    "render_overview",
    "match_module",
    "init_slots",
    "record_answer",
    "format_question",
    "format_confirm",
    "run_fields",
]
