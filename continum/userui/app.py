from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger("continum.userui")


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP VALIDATION
# ─────────────────────────────────────────────────────────────────────────────


def _validate_startup(db) -> list[str]:
    failures = []
    required_views = ["silver_inquiries", "gold_experiment_analysis"]
    for view in required_views:
        try:
            db.execute(f"SELECT 1 FROM {view} LIMIT 1")
        except Exception as e:
            failures.append(f"{view}: {e}")
    return failures


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY
# ─────────────────────────────────────────────────────────────────────────────


def create_app(data_dir: str = "./sample_data", debug: bool = False):
    try:
        from flask import Flask
    except ImportError:
        raise ImportError("pip install flask")

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.environ.get("CONTINUM_SECRET", "continum-dev-key")
    app.config["DATA_DIR"] = data_dir

    # ── SSE queue registry ────────────────────────────────────────────────────
    app.stream_queues: dict = {}

    # ── Boot-readiness signal ────────────────────────────────────────────────
    app._boot_event: threading.Event = threading.Event()
    app._boot_error: Optional[str] = None

    # ── Singletons (canonical names) ─────────────────────────────────────────
    from continum.datastore.memory import get_memory
    from continum.experimentation.enterprise import get_audit, get_governance, get_snapshots
    from continum.insights.insight_bus import get_bus
    from continum.insights.session import get_session

    app.ses = get_session()
    app.bus = get_bus()
    app.mem = get_memory()
    app.aud = get_audit()
    app.gov = get_governance()
    app.snap = get_snapshots()
    app.db = None
    app.state = None
    app.llm = None

    # ── Back-compat properties for execute.py (continum_* aliases) ───────────
    #    These kept for any code that still uses the old attribute names.
    app.__class__.continum_db = property(lambda self: self.db)
    app.__class__.continum_session = property(lambda self: self.ses)
    app.__class__.continum_state = property(lambda self: self.state)
    app.__class__.continum_bus = property(lambda self: self.bus)

    # ── Boot (runs in daemon thread — Flask is available immediately) ─────────
    def _boot():
        try:
            import duckdb

            from continum.contextmate.bootstrap import bootstrap_from_connection
            from continum.datastore.loader import (
                build_gold_layer,
                build_silver_layer,
                load_csvs,
                register_bronze,
            )

            db = duckdb.connect(":memory:")
            state = bootstrap_from_connection(
                mode="duckdb",
                client_name=app.ses.client_name,
                db=db,
            )
            ds = load_csvs(data_dir)
            register_bronze(db, ds)
            build_silver_layer(db)
            build_gold_layer(db)

            # ── Startup validation ────────────────────────────────────────────
            failures = _validate_startup(db)
            if failures:
                for f in failures:
                    logger.warning("Startup validation failed: %s", f)
                    app.bus.warn("boot", f"View missing: {f}")

            app.db = db
            app.state = state
            app.ses.db = db
            app.ses.state = state

            app.bus.success("ui", f"UI ready — {len(ds)} datasets loaded")
            app.aud.record("boot", "ui", {"data_dir": data_dir, "datasets": list(ds)})
            logger.info("UI DB booted from %s", data_dir)

            # Narrative opening
            try:
                from continum.askdata.narrative_runtime import get_narrative

                get_narrative(bus=app.bus, session=app.ses, memory=app.mem).open_session()
            except Exception:
                pass

            # LLM — background, non-blocking
            try:
                from continum.crosscutting.llm import load_llm, require_llm

                app.llm = require_llm()

                def _load_llm():
                    try:
                        load_llm()
                        app.bus.success(
                            "llm", f"LLM loaded on {app.llm.status().get('device', 'unknown')}"
                        )
                    except Exception as e2:
                        app.bus.warn("llm", f"LLM load failed: {str(e2)[:120]}")

                threading.Thread(target=_load_llm, daemon=True).start()
            except Exception as e:
                logger.warning("LLM init failed: %s", e)

            app._boot_event.set()

        except Exception as e:
            app._boot_error = str(e)
            app._boot_event.set()  # unblock waiters even on failure
            logger.error("UI DB boot failed: %s", e, exc_info=True)
            app.bus.warn("ui", f"DB init failed: {e}")

    threading.Thread(target=_boot, daemon=True, name="continum-boot").start()

    # ── Blueprints ────────────────────────────────────────────────────────────
    from continum.userui.routes.api import bp as api_bp
    from continum.userui.routes.pages import bp as pages_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(pages_bp)
    # execute.py blueprint NOT registered — api.py owns all /api/ routes
    # to prevent duplicate route conflicts that kill SSE connections

    # ── Health endpoint ───────────────────────────────────────────────────────
    from flask import jsonify as _jsonify

    @app.route("/health")
    def health():
        ready = app.db is not None and app._boot_event.is_set() and not app._boot_error
        status = {
            "status": "ok" if ready else "booting",
            "db_ready": app.db is not None,
            "boot_error": app._boot_error,
            "llm_loaded": app.llm is not None,
        }
        return _jsonify(status), (200 if ready else 503)

    @app.route("/readyz")
    def readyz():
        app._boot_event.wait(timeout=60)
        if app.db is None or app._boot_error:
            return _jsonify({"ready": False, "error": app._boot_error}), 503
        return _jsonify({"ready": True}), 200

    return app


def run(host="0.0.0.0", port=5050, data_dir="./sample_data", debug=False):
    app = create_app(data_dir=data_dir, debug=debug)
    print("\n  🔬 CONTINUM OS — Visual Operator Console")
    print(f"  ➜  http://localhost:{port}\n")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    run()
