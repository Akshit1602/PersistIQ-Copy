"""Regression guards for the MatchView Copilot UI/UX fixes (see docs/MV_FIXES.md).

These lock in behaviour that previously broke:
  * the Ask-AI chat pane leaking onto the Insights/Narrative/Evidence tabs,
  * the tool-confirmation prompt not saying what the tool would do,
  * experiment-scoped modules running with no experiment selected,
  * modules showing a generic "Run this module." description.
"""

from __future__ import annotations


# ── A9: the confirmation prompt describes what the tool will do ───────────────
def test_confirmation_message_includes_tool_description():
    from continum.orchestrator import confirmation_message, get_tool

    tool = get_tool("email_analytics")
    msg = confirmation_message(tool)
    assert tool.module_name in msg
    # the tool's own description text must be surfaced before the user confirms
    assert "performance analytics" in msg.lower()


# ── A7: experiment-scoped tools call out a missing experiment ─────────────────
def test_needs_experiment_callout():
    from continum.orchestrator import get_tool
    from continum.userui.routes import api

    class _Ses:  # no active experiment
        active_experiment = ""

    class _App:
        ses = _Ses()

    app = _App()
    health = get_tool("health")  # target=health_monitor (scoped)
    email = get_tool("email_analytics")  # target=askdata (not scoped)

    assert api._needs_experiment_callout(health, app, {}) is not None
    assert api._needs_experiment_callout(email, app, {}) is None
    # an experiment in ui_context satisfies the requirement -> no callout
    assert api._needs_experiment_callout(health, app, {"active_experiment": "exp_x"}) is None


# ── A10: every module shows a real description when clicked ───────────────────
def test_module_config_falls_back_to_registry_description():
    from continum.userui.routes.api import _get_module_config

    cfg = _get_module_config("anomaly_synthesis", None)
    assert cfg["description"] and cfg["description"] != "Run this module."


# ── A1: the Ask-AI pane only renders on its own tab (no inline display leak) ──
def test_ask_pane_not_forced_visible_inline():
    from continum.userui.templates.dashboard import DASHBOARD

    # The old bug: id="tab-ask" carried inline display:flex, overriding
    # .rp-panel{display:none} and leaking the chat onto every tab.
    assert 'id="tab-ask" style="display:flex' not in DASHBOARD
    # The replacement CSS gates visibility on the active class.
    assert "#tab-ask.show{display:flex}" in DASHBOARD


# ── A3 / A6: evidence + collapsible SQL/viz helpers are present ───────────────
def test_dashboard_has_evidence_and_collapsible_helpers():
    from continum.userui.templates.dashboard import DASHBOARD

    assert "function renderEvidence()" in DASHBOARD
    assert "function captureEvidence(" in DASHBOARD
    assert "function _cpDetails(" in DASHBOARD  # collapsible builder
    assert "ensurePlotly" in DASHBOARD  # chart rendering
