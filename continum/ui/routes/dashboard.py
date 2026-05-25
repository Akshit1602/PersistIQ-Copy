from __future__ import annotations
from flask import Blueprint, current_app, render_template_string
from continum.ui.templates.pages import DASHBOARD_HTML

bp = Blueprint("dashboard", __name__)

@bp.route("/")
def index():
    app    = current_app._get_current_object()
    bus    = app.continum_bus
    session= app.continum_session
    memory = app.continum_memory

    insights    = [_ins_dict(i) for i in bus.all()[-15:]]
    warnings    = [_ins_dict(i) for i in bus.warnings()]
    recs        = [_ins_dict(i) for i in bus.recommendations()]
    history     = [_rec_dict(r) for r in session.execution_history[-10:]]
    session_recs= [{"action": r.action, "reason": r.reason, "priority": r.priority}
                   for r in session.recommendations[:5]]

    return render_template_string(DASHBOARD_HTML,
        session_id   = session.session_id,
        client_name  = session.client_name,
        active_exp   = session.active_experiment or "—",
        active_metrics=", ".join(session.active_metrics[:5]) or "—",
        n_runs       = len(session.execution_history),
        n_memory     = memory.experiment_count(),
        insights     = insights,
        warnings     = warnings,
        recs         = recs,
        history      = history,
        session_recs = session_recs,
    )

def _ins_dict(i):
    return {"type": i.insight_type, "severity": i.severity,
            "source": i.source_module, "message": i.message,
            "detail": i.detail, "created_at": i.created_at[:19]}

def _rec_dict(r):
    return {"module": r.module, "phase": r.phase,
            "ok": r.ok, "elapsed": round(r.elapsed_s, 2), "summary": r.summary[:80]}
