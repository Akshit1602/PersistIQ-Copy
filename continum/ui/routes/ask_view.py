from flask import Blueprint, current_app, request, jsonify
bp = Blueprint("ask_view", __name__)

@bp.route("/api/ask", methods=["POST"])
def ask():
    app  = current_app._get_current_object()
    body = request.get_json(silent=True) or {}
    q    = body.get("question", "").strip()
    ui_context  = body.get("ui_context", {})

    if not q:
        return jsonify({"error": "No question provided"}), 400

    from continum.utils.rag import get_readme_context
    readme_context = get_readme_context(q)

    # Unified engine: AskData handles everything now
    from continum.runtime.askdata_engine import AskDataEngine
    engine = AskDataEngine(db=app.continum_db)

    # We pass readme_context as history
    result = engine.ask(
        q,
        history=readme_context,
        ui_context=ui_context,
        session=app.continum_session,
        bus=app.continum_bus,
        memory=app.continum_memory
    )

    # Check if result is a dict (new unified engine) or just a string (old)
    if isinstance(result, dict):
        response = result.get("answer")
        # You can also include other parts if the UI supports it
        return jsonify({
            "question": q,
            "response": response,
            "chain": result.get("chain"),
            "sql": result.get("sql")
        })
    else:
        return jsonify({"question": q, "response": result})
