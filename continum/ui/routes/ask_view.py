from flask import Blueprint, current_app, request, jsonify
bp = Blueprint("ask_view", __name__)

@bp.route("/api/ask", methods=["POST"])
def ask():
    app  = current_app._get_current_object()
    body = request.get_json(silent=True) or {}
    q    = body.get("question", "").strip()
    if not q:
        return jsonify({"error": "No question provided"}), 400
    from continum.runtime.ask import ContinumCopilot
    copilot  = ContinumCopilot(
        session=app.continum_session,
        bus    =app.continum_bus,
        memory =app.continum_memory,
    )
    response = copilot.ask(q)
    return jsonify({"question": q, "response": response})
