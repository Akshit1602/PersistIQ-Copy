from flask import Blueprint, current_app, jsonify
bp = Blueprint("session_view", __name__)

@bp.route("/api/session")
def session_state():
    app = current_app._get_current_object()
    s   = app.continum_session
    return jsonify({
        "session_id":       s.session_id,
        "client_name":      s.client_name,
        "active_experiment":s.active_experiment,
        "active_metrics":   s.active_metrics,
        "n_runs":           len(s.execution_history),
        "history": [{"module": r.module, "ok": r.ok,
                     "elapsed": round(r.elapsed_s, 2), "summary": r.summary}
                    for r in s.execution_history[-20:]],
        "recommendations": [{"action": r.action, "reason": r.reason}
                             for r in s.recommendations[:5]],
    })

@bp.route("/api/intelligence")
def intelligence():
    app = current_app._get_current_object()
    bus = app.continum_bus
    return jsonify({
        "insights":      [_d(i) for i in bus.all()[-30:]],
        "warnings":      [_d(i) for i in bus.warnings()],
        "recommendations":[_d(i) for i in bus.recommendations()],
        "kpis":          [_d(i) for i in bus.kpi_suggestions()],
    })

def _d(i):
    return {"type": i.insight_type, "severity": i.severity,
            "source": i.source_module, "message": i.message,
            "detail": i.detail}
