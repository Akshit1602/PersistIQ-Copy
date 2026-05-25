from __future__ import annotations
import json
import queue
import threading
import time
import logging
import uuid as _uuid
from typing import Any

from flask import Blueprint, current_app, request, Response, jsonify

bp     = Blueprint("execute", __name__)
logger = logging.getLogger("continum.ui.execute")

# Per-session write lock — keyed by session_id (or "__global__" if none)
_SESSION_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_MUTEX = threading.Lock()

_MAX_RETRIES     = int(__import__("os").environ.get("CONTINUM_EXEC_RETRIES", "1"))
_RETRY_BASE_WAIT = 0.5   # seconds


def _session_lock(session_id: str) -> threading.Lock:
    with _LOCKS_MUTEX:
        if session_id not in _SESSION_LOCKS:
            _SESSION_LOCKS[session_id] = threading.Lock()
        return _SESSION_LOCKS[session_id]


def _structured_error(code: str, msg: str, module: str = "", run_id: str = "") -> str:
    return json.dumps({
        "level":  "ERR",
        "code":   code,
        "msg":    msg,
        "module": module,
        "run_id": run_id,
        "ts":     time.time(),
    })


def _structured_event(level: str, msg: str, **extra) -> str:
    payload = {"level": level, "msg": msg, "ts": time.time()}
    payload.update(extra)
    return json.dumps(payload)


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTION ROUTE
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/api/execute/<module_key>", methods=["POST"])
def execute_module(module_key: str):
    app    = current_app._get_current_object()
    run_id = str(_uuid.uuid4())[:8]
    q: queue.Queue = queue.Queue(maxsize=500)
    app.stream_queues[run_id] = q

    body        = request.get_json(silent=True) or {}
    # ── Null-session guard ─────────────────────────────────────────────────
    active_exp  = ""
    if app.ses is not None:
        active_exp = app.ses.active_experiment or ""
    exp_name    = body.get("experiment_name") or active_exp
    extra_kw    = body.get("params") or {}
    max_retries = int(body.get("max_retries", _MAX_RETRIES))

    # ── Execution-state validation ─────────────────────────────────────────
    if not app._boot_event.is_set():
        q.put(_structured_error("DB_NOT_READY", "DB still booting — retry in a moment",
                                module=module_key, run_id=run_id))
        q.put(_structured_event("DONE", "__done__", run_id=run_id))
        return jsonify({"run_id": run_id, "error": "booting"})

    if app.db is None:
        q.put(_structured_error("DB_UNAVAILABLE", "DB unavailable — check /health",
                                module=module_key, run_id=run_id))
        q.put(_structured_event("DONE", "__done__", run_id=run_id))
        return jsonify({"run_id": run_id, "error": "no_db"})

    # ── Worker ────────────────────────────────────────────────────────────
    def _emit(level: str, msg: str, **kw):
        if not q.full():
            q.put(_structured_event(level, msg, run_id=run_id, **kw))

    def _run_once() -> Any:
        from continum.api.dispatcher import run_module, _build_registry
        _build_registry()

        kw: dict = dict(extra_kw)
        if exp_name and module_key in (
            "experiment_analysis", "health_monitor", "sequential_testing",
            "causal_analysis", "pre_post_analysis", "simpsons_paradox",
            "roi_tracker", "uplift_modeller", "decision_engine",
        ):
            kw.setdefault("experiment_name", exp_name)
            kw.setdefault("experiment_id",   exp_name)

        return run_module(
            module_key,
            state=app.state,
            llm=app.llm,
            db=app.db,
            **kw,
        )

    def _worker():
        ses_id = (app.ses.session_id if app.ses else "__global__")
        lock   = _session_lock(ses_id)

        try:
            _emit("INFO", f"Starting {module_key}…")
            t0 = time.monotonic()

            # ── Retry loop ────────────────────────────────────────────────
            result    = None
            last_err  = None
            for attempt in range(max_retries + 1):
                if attempt > 0:
                    wait = _RETRY_BASE_WAIT * (2 ** (attempt - 1))
                    _emit("WARN", f"Retry {attempt}/{max_retries} after {wait:.1f}s…")
                    time.sleep(wait)
                try:
                    result = _run_once()
                    last_err = None
                    break
                except Exception as exc:
                    last_err = exc
                    logger.warning("Execute %s attempt %d failed: %s",
                                   module_key, attempt + 1, exc)

            elapsed = time.monotonic() - t0

            if last_err is not None:
                _emit("ERR", f"{module_key} failed after {max_retries + 1} attempt(s): {last_err}",
                      code="MODULE_ERROR", module=module_key)
                _emit("DONE", "__done__")
                return

            # ── Session write (locked) ────────────────────────────────────
            with lock:
                if app.ses is not None:
                    app.ses.set(f"{module_key}_result", result)
                    app.ses.set("experiment_result", result)
                    try:
                        from continum.runtime.shell.executor import _summarise
                        summary = _summarise(result, module_key)
                    except Exception:
                        summary = str(type(result).__name__)
                    app.ses.record_run(module_key, "ui", elapsed, ok=True, summary=summary)
                    app.ses.save()

            # ── Intelligence bus ──────────────────────────────────────────
            try:
                from continum.runtime.intelligence import publish_next_steps
                publish_next_steps(module_key, app.bus)
            except Exception:
                pass

            _emit("OK",   f"{module_key} completed in {elapsed:.2f}s", module=module_key)
            _emit("DONE", "__done__")

        except Exception as e:
            q.put(_structured_error("WORKER_ERROR", str(e), module=module_key, run_id=run_id))
            q.put(_structured_event("DONE", "__done__", run_id=run_id))
            logger.exception("Execute worker %s failed", module_key)
        finally:
            # Cleanup the queue reference after a grace period
            def _deferred_cleanup():
                time.sleep(120)
                app.stream_queues.pop(run_id, None)
            threading.Thread(target=_deferred_cleanup, daemon=True).start()

    threading.Thread(target=_worker, daemon=True, name=f"exec-{module_key}-{run_id}").start()
    return jsonify({"run_id": run_id})


# ─────────────────────────────────────────────────────────────────────────────
# SSE STREAM
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/api/stream/<run_id>")
def stream(run_id: str):
    app = current_app._get_current_object()
    q   = app.stream_queues.get(run_id)
    if q is None:
        err = _structured_error("UNKNOWN_RUN", f"No stream for run_id={run_id}", run_id=run_id)
        return Response(f"data: {err}\n\n", mimetype="text/event-stream")

    def _generate():
        while True:
            try:
                msg  = q.get(timeout=30)
                yield f"data: {msg}\n\n"
                data = json.loads(msg)
                if data.get("msg") == "__done__":
                    app.stream_queues.pop(run_id, None)
                    break
            except queue.Empty:
                yield f"data: {_structured_event('PING', '…', run_id=run_id)}\n\n"

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT SELECT  (non-duplicate version of api.py endpoint)
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/api/session/select-experiment", methods=["POST"])
def select_experiment():
    app  = current_app._get_current_object()
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    # ── Null-session guard ─────────────────────────────────────────────────
    if app.ses is None:
        return jsonify({"ok": False, "error": "session not initialised"}), 503
    if name:
        app.ses.select_experiment(name)
        app.ses.save()
        if app.aud:
            app.aud.record("select_experiment", name, session_id=app.ses.session_id)
    return jsonify({"ok": True, "active": app.ses.active_experiment})
