from flask import Blueprint, current_app, render_template_string
from continum.ui.templates.dashboard import DASHBOARD

bp = Blueprint("pages", __name__)

@bp.route("/")
def index():
    app = current_app._get_current_object()
    s   = app.ses
    return render_template_string(DASHBOARD,
        session_id   = s.session_id,
        client_name  = s.client_name,
        active_exp   = s.active_experiment or "—",
        n_runs       = len(s.execution_history),
        n_memory     = app.mem.experiment_count(),
        active_metrics=", ".join(s.active_metrics[:4]) or "—",
    )
