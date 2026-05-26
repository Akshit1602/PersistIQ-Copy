from flask import Blueprint, current_app, request, jsonify
bp = Blueprint("ask_view", __name__)

@bp.route("/api/ask", methods=["POST"])
def ask():
    app  = current_app._get_current_object()
    body = request.get_json(silent=True) or {}
    q    = body.get("question", "").strip()
    engine_type = body.get("engine", "copilot")
    ui_context  = body.get("ui_context", {})

    if not q:
        return jsonify({"error": "No question provided"}), 400

    from continum.utils.rag import get_readme_context
    readme_context = get_readme_context(q)

    if engine_type == "askdata":
        from continum.runtime.askdata_engine import AskDataEngine
        engine = AskDataEngine(db=app.continum_db)
        # We can pass readme_context as part of history or initial state if needed
        response = engine.ask(q, history=readme_context, ui_context=ui_context)
    else:
        from continum.runtime.ask import ContinumCopilot
        copilot  = ContinumCopilot(
            session=app.continum_session,
            bus    =app.continum_bus,
            memory =app.continum_memory,
        )
        # Augment question with readme context if it seems like a meta-question
        augmented_q = q
        if any(kw in q.lower() for kw in ["how", "what is", "tell me about", "persist", "askdata"]):
            augmented_q = f"{q}\n\nRelevant documentation context:\n{readme_context}"

        response = copilot.ask(augmented_q)

    return jsonify({"question": q, "response": response})
