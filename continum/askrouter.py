"""
LLM-first tool router for the Continum Copilot.

The legacy router was a hand-rolled if/elif ladder over five independent keyword
matchers (``orchestrator.detect_tool``, ``api._auto_mode``, ``api._is_meta_q``,
``intentanalyser.detect_intent``, ``flow.match_module``). Only 6 of the ~38
registered modules were reachable from chat, and any paraphrase or typo that
missed every keyword fell through to a slow NL->SQL answer.

This module replaces that selection step with ONE structured LLM call that
classifies a message into exactly one action over the full tool catalog:

    tool   — run one of the primary MatchView modules (confirm gate applies)
    module — run a more specialised analysis module (inputs collected via a form)
    data   — answer by querying the dataset (NL -> SQL via AskData)
    guide  — how-to / capability / "what can you do"
    meta   — recommendations / session summary

``llm_route`` is deliberately conservative: it returns ``None`` (so the caller
falls back to the keyword ladder) whenever the LLM is not configured, the call
fails, the response can't be parsed, or the chosen target isn't valid. It never
raises. This keeps the copilot working offline / without an API key.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("continum.askrouter")

_VALID_ACTIONS = {"tool", "module", "data", "guide", "meta"}

# MatchView tool targets that are already represented as first-class "tool"
# choices — they must not also appear in the specialised "module" list.
_MATCHVIEW_TARGETS = {
    "uplift_modeller",
    "audience_selection",
    "experiment_analysis",
    "causal_analysis",
    "health_monitor",
}

_ROUTER_SYSTEM = (
    "You are a routing classifier for an experimentation-analytics copilot. "
    "Given a user message, choose exactly ONE action. "
    "Respond with ONLY a single JSON object — no prose, no markdown, no code fences."
)


def _matchview_tools() -> List[Any]:
    try:
        from continum.orchestrator import MATCHVIEW_TOOLS

        return list(MATCHVIEW_TOOLS)
    except Exception:
        return []


def _module_catalog() -> List[Dict[str, str]]:
    """Specialised modules (everything not already a MatchView tool target)."""
    try:
        from continum.toolinterface import list_modules

        mods = list_modules()
    except Exception:
        return []
    out = []
    for m in mods:
        name = m.get("name", "")
        if not name or name in _MATCHVIEW_TARGETS:
            continue
        out.append({"name": name, "description": (m.get("description") or "").strip()})
    return out


def _build_prompt(
    question: str, ui_context: Optional[dict], tools: List[Any], modules: List[Dict[str, str]]
) -> str:
    exp = ""
    if ui_context:
        exp = ui_context.get("active_experiment") or ""

    tool_lines = []
    for t in tools:
        desc = (getattr(t, "description", "") or "").rstrip(".")
        tool_lines.append(f'  - key "{t.key}" — {t.module_name}: {desc}')

    mod_lines = []
    for m in modules:
        desc = (m["description"] or "").rstrip(".")
        # keep each line bounded so a large catalog stays readable to the model
        if len(desc) > 110:
            desc = desc[:107] + "..."
        mod_lines.append(f'  - "{m["name"]}" — {desc}')

    return (
        f'User message: "{question}"\n'
        f'Active experiment: {exp or "(none set)"}\n\n'
        "Choose ONE action:\n\n"
        '1) "tool" — the user wants to RUN one of these primary modules '
        "(the app will ask the user to confirm before running). Pick the best key:\n"
        + "\n".join(tool_lines)
        + "\n\n"
        '2) "module" — the user wants to run a more specialised analysis module '
        "(its inputs are collected via a form). Pick the module name:\n"
        + "\n".join(mod_lines)
        + "\n\n"
        '3) "data" — a question answerable by querying the dataset: metrics (IOR, '
        "AOV, conversion), counts, breakdowns by segment/variant, trends, "
        'comparisons. e.g. "what is the current IOR", "conversion by variant".\n\n'
        '4) "guide" — how-to / capability / "what can you do" / how the tool works.\n\n'
        '5) "meta" — recommendation or session questions: "what should I run next", '
        '"summarise this session".\n\n'
        'Rules: if unsure between a tool/module and a data question, prefer "data". '
        'Only choose "tool" or "module" when the user clearly wants to RUN something.\n\n'
        "Return JSON exactly like: "
        '{"action":"tool|module|data|guide|meta","key":"<tool key or empty>",'
        '"module":"<module name or empty>","reason":"<short>"}'
    )


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort parse of a JSON object from an LLM response."""
    if not text:
        return None
    s = text.strip()
    # strip code fences if the model added them despite instructions
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s).rstrip("`").strip()
    # grab the first {...} block
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _validate(obj: Dict[str, Any], valid_keys: set, valid_modules: set) -> Optional[Dict[str, str]]:
    """Coerce a raw decision into a validated, actionable decision (or None)."""
    action = str(obj.get("action", "")).strip().lower()
    key = str(obj.get("key", "") or "").strip()
    module = str(obj.get("module", "") or "").strip()
    reason = str(obj.get("reason", "") or "").strip()[:200]

    if action not in _VALID_ACTIONS:
        return None

    if action == "tool":
        if key not in valid_keys:
            return None
        return {"action": "tool", "key": key, "module": "", "reason": reason}

    if action == "module":
        # A model may name a MatchView target as a "module" — route it through the
        # nicer tool/confirm path instead.
        if module in _MATCHVIEW_TARGETS:
            tkey = _target_to_tool_key(module)
            if tkey:
                return {"action": "tool", "key": tkey, "module": "", "reason": reason}
        if module not in valid_modules:
            return None
        return {"action": "module", "key": "", "module": module, "reason": reason}

    # data / guide / meta carry no target
    return {"action": action, "key": "", "module": "", "reason": reason}


def _target_to_tool_key(target: str) -> Optional[str]:
    for t in _matchview_tools():
        if getattr(t, "target", None) == target:
            return t.key
    return None


def llm_route(app, question: str, ui_context: Optional[dict] = None) -> Optional[Dict[str, str]]:
    """Return a validated routing decision, or None to fall back to keyword routing.

    Never raises. Returns None when the LLM is unconfigured / errors / abstains.
    """
    q = (question or "").strip()
    if not q:
        return None

    llm = getattr(app, "llm", None)
    if llm is None or not getattr(llm, "is_loaded", False):
        return None  # no cloud LLM → caller uses the keyword fallback

    tools = _matchview_tools()
    modules = _module_catalog()
    if not tools and not modules:
        return None

    valid_keys = {t.key for t in tools}
    valid_modules = {m["name"] for m in modules}

    try:
        prompt = _build_prompt(q, ui_context, tools, modules)
        raw = llm.ask(prompt, system=_ROUTER_SYSTEM)
    except Exception as e:  # noqa: BLE001 — routing must never break the request
        logger.debug("llm_route LLM call failed: %s", e)
        return None

    if not raw or raw.startswith("[LLM "):  # client sentinels for error/not-configured
        return None

    obj = _extract_json(raw)
    if obj is None:
        logger.debug("llm_route could not parse decision: %r", raw[:200])
        return None

    decision = _validate(obj, valid_keys, valid_modules)
    if decision is None:
        logger.debug("llm_route invalid decision: %r", obj)
        return None

    logger.info(
        "llm_route → %s (%s%s)",
        decision["action"],
        decision.get("key") or decision.get("module") or "-",
        f": {decision['reason']}" if decision.get("reason") else "",
    )
    return decision


__all__ = ["llm_route"]
