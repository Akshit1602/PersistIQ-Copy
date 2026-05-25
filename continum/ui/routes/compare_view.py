from flask import Blueprint, current_app, request, jsonify
bp = Blueprint("compare_view", __name__)

@bp.route("/api/compare", methods=["POST"])
def compare():
    app  = current_app._get_current_object()
    body = request.get_json(silent=True) or {}
    a    = body.get("experiment_a", "").strip()
    b    = body.get("experiment_b", "").strip()
    if not a or not b:
        return jsonify({"error": "Provide experiment_a and experiment_b"}), 400

    from continum.runtime.compare import _extract_metrics, _synthesise
    from continum.api.dispatcher  import run_module, _build_registry
    _build_registry()

    results = {}
    for name in [a, b]:
        try:
            r = run_module("experiment_analysis",
                           state=app.continum_state, llm=None,
                           db=app.continum_db,
                           experiment_name=name, experiment_id=name)
            results[name] = r
            if r:
                app.continum_memory.record_experiment(name, name, r)
        except Exception as e:
            results[name] = None

    m_a = _extract_metrics(results.get(a))
    m_b = _extract_metrics(results.get(b))
    narrative = _synthesise(a, m_a, b, m_b)

    return jsonify({
        "experiment_a": {"name": a, "metrics": _serialise(m_a)},
        "experiment_b": {"name": b, "metrics": _serialise(m_b)},
        "narrative":    narrative,
    })

def _serialise(m):
    return {k: v for k, v in m.items() if k not in ("slices", "guardrails")}
