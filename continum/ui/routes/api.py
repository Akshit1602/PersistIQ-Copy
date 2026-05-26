from __future__ import annotations
import json, logging, queue, threading, time, uuid
from flask import Blueprint, current_app, jsonify, request, Response

bp     = Blueprint("api", __name__, url_prefix="/api")
logger = logging.getLogger("continum.ui.api")


# ── helpers ────────────────────────────────────────────────────────────────────
def _app():
    return current_app._get_current_object()


# ── experiments ───────────────────────────────────────────────────────────────


@bp.route("/stop/<run_id>", methods=["POST"])
def stop_run(run_id: str):
    app = _app()
    stop_events = getattr(app, "stop_events", {})
    if run_id in stop_events:
        stop_events[run_id].set()
        # Also put a DONE event in the queue so the SSE stream closes
        q = app.stream_queues.get(run_id)
        if q and not q.full():
            q.put(json.dumps({"level":"WARN","msg":"⛔ Stopped by user","ts":time.time()}))
            q.put(json.dumps({"level":"DONE","msg":"__done__","ts":time.time()}))
        return jsonify({"ok": True, "run_id": run_id})
    return jsonify({"ok": False, "error": "unknown_run_id"}), 404

@bp.route("/experiments")
def experiments():
    app = _app()
    if not app.db:
        return jsonify([])
    try:
        from continum.app.loader import list_experiments
        df = list_experiments(app.db)
        return jsonify(df.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/experiments/select", methods=["POST"])
def select_experiment():
    app  = _app()
    name = (request.get_json(silent=True) or {}).get("name", "")
    if name:
        app.ses.select_experiment(name)
        app.ses.save()
        app.aud.record("select_experiment", name, session_id=app.ses.session_id)
    return jsonify({"ok": True, "active": app.ses.active_experiment})


# ── modules list ──────────────────────────────────────────────────────────────
@bp.route("/modules")
def modules():
    from continum.api.dispatcher import list_modules, _build_registry
    _build_registry()
    return jsonify(list_modules())


# ── Module configuration (pre-run form fields with DB-detected defaults) ─────
@bp.route("/module-config/<module_key>")
def module_config(module_key: str):
    app = _app()
    cfg = _get_module_config(module_key, app.db)
    return jsonify(cfg)


def _get_module_config(module_key: str, db) -> dict:
    baselines = {}
    if db:
        try:
            row = db.execute("""
                SELECT
                    COUNT(*) / NULLIF(DATEDIFF('day',MIN(created_at),MAX(created_at)),0) AS daily_inq,
                    AVG(CAST(converted_to_order AS DOUBLE))                               AS ior,
                    COUNT(*) / 30.0                                                       AS monthly_inq,
                    AVG(COALESCE(order_value,0))                                          AS aov
                FROM silver_inquiries
            """).fetchone()
            if row:
                baselines = {
                    "daily_inquiries": round(float(row[0] or 500), 0),
                    "ior":             round(float(row[1] or 0.18), 4),
                    "monthly_inquiries": round(float(row[2] or 10000), 0),
                    "aov":             round(float(row[3] or 500), 0),
                }
        except Exception:
            baselines = {"daily_inquiries": 500, "ior": 0.18, "monthly_inquiries": 10000, "aov": 500}

    ior  = baselines.get("ior", 0.18)
    dau  = baselines.get("daily_inquiries", 500)
    mon  = baselines.get("monthly_inquiries", 10000)
    aov  = baselines.get("aov", 500)

    # Experiment list for selector fields
    experiments = []
    if db:
        try:
            rows = db.execute("""
                SELECT DISTINCT experiment_name,
                       COUNT(*) AS n,
                       COUNT(DISTINCT variant) AS variants
                FROM gold_experiment_analysis
                GROUP BY experiment_name ORDER BY n DESC
            """).fetchall()
            experiments = [{"name": r[0], "n": int(r[1]), "variants": int(r[2])} for r in rows]
        except Exception:
            pass

    CONFIGS = {
        "power_calculator": {
            "title": "⚡ Power Calculator",
            "description": "Calculate required sample size and experiment duration from your baseline data.",
            "needs_experiment": False,
            "fields": [
                {"key": "Baseline conversion/IOR rate (0–1)", "label": "Baseline IOR rate (0–1)",
                 "type": "float", "default": ior, "min": 0.001, "max": 0.999,
                 "help": f"Auto-detected from historical data: {ior:.4f}"},
                {"key": "MDE — minimum detectable effect (% relative, e.g. 10)", "label": "Minimum detectable effect (% relative)",
                 "type": "float", "default": 10.0, "min": 0.1, "help": "e.g. 10 means detect a 10% relative lift"},
                {"key": "Significance level α", "label": "Significance level α",
                 "type": "float", "default": 0.05, "min": 0.001, "max": 0.30},
                {"key": "Statistical power 1-β", "label": "Statistical power 1−β",
                 "type": "float", "default": 0.80, "min": 0.50, "max": 0.99},
                {"key": "Number of variants (including control)", "label": "Number of variants (incl. control)",
                 "type": "int", "default": 2, "min": 2},
                {"key": "Daily eligible traffic", "label": "Daily eligible traffic",
                 "type": "float", "default": dau, "min": 1,
                 "help": f"Auto-detected: {dau:,.0f} daily inquiries"},
                {"key": "Fraction of traffic in experiment (0–1)", "label": "Traffic fraction in experiment (0–1)",
                 "type": "float", "default": 1.0, "min": 0.01, "max": 1.0},
            ],
        },
        "opportunity_sizing": {
            "title": "📋 Opportunity Sizing",
            "description": "Quantify the revenue opportunity before committing to an experiment.",
            "needs_experiment": False,
            "fields": [
                {"key": "monthly_inquiries", "label": "Monthly inquiries",
                 "type": "float", "default": mon, "min": 1,
                 "help": f"Auto-detected: {mon:,.0f}/month"},
                {"key": "current_ior_(0–1)", "label": "Current IOR (0–1)",
                 "type": "float", "default": ior, "min": 0.001, "max": 0.999,
                 "help": f"Auto-detected: {ior:.4f}"},
                {"key": "target_ior_after_experiment_(0–1)", "label": "Target IOR after experiment",
                 "type": "float", "default": round(min(ior * 1.10, 0.999), 4), "min": 0.001, "max": 0.999},
                {"key": "average_order_value_($)", "label": "Average order value ($)",
                 "type": "float", "default": aov, "min": 1,
                 "help": f"Auto-detected: ${aov:,.0f}"},
                {"key": "gross_margin_(0–1)", "label": "Gross margin (0–1)",
                 "type": "float", "default": 0.30, "min": 0.01, "max": 1.0},
                {"key": "time_horizon_(months)", "label": "Time horizon (months)",
                 "type": "float", "default": 12.0, "min": 1},
            ],
        },
        "brief_generator": {
            "title": "📄 Experiment Brief Generator",
            "description": "Generate a structured experiment brief with hypothesis, metrics, and design.",
            "needs_experiment": False,
            "fields": [
                {"key": "description", "label": "Feature / change description", "type": "text",
                 "default": "", "help": "What are you testing? Be specific."},
                {"key": "hypothesis", "label": "Hypothesis (if X then Y because Z)", "type": "text",
                 "default": "", "help": "e.g. If we move billing earlier, then IOR will increase by 5% because..."},
                {"key": "team", "label": "Team", "type": "text", "default": "Product"},
                {"key": "owner", "label": "Experiment owner", "type": "text", "default": "Analyst"},
            ],
        },
        "metrics_and_tracking": {
            "title": "📊 KPI & Tracking Plan",
            "description": "Define primary, secondary, and guardrail metrics with tracking events.",
            "needs_experiment": False,
            "fields": [
                {"key": "description", "label": "Feature description", "type": "text",
                 "default": "", "help": "Brief description of the feature being tracked"},
                {"key": "maturity", "label": "Experiment maturity",
                 "type": "select", "default": "mvp",
                 "options": ["mvp", "iteration", "critical"],
                 "help": "mvp=first test, iteration=refined, critical=high-stakes"},
            ],
        },
        "audience_selection": {
            "title": "👥 Audience Selection",
            "description": "Define who goes into control and treatment based on propensity rules.",
            "needs_experiment": False,
            "fields": [
                {"key": "category", "label": "Experiment category",
                 "type": "select", "default": "conversion",
                 "options": ["conversion", "acquisition", "retention", "engagement"],
                 "help": "Determines which propensity rules apply"},
            ],
        },
        "health_monitor": {
            "title": "🩺 Experiment Health Monitor",
            "description": "SRM detection, guardrail checks, and ETA to significance.",
            "needs_experiment": True,
            "fields": [
                {"key": "experiment_name", "label": "Experiment to monitor",
                 "type": "experiment_select", "default": "",
                 "options": experiments},
            ],
        },
        "sequential_testing": {
            "title": "📈 Sequential Testing (mSPRT)",
            "description": "Always-valid p-values for early stopping decisions.",
            "needs_experiment": True,
            "fields": [
                {"key": "experiment_name", "label": "Experiment",
                 "type": "experiment_select", "default": "",
                 "options": experiments},
                {"key": "alpha", "label": "Type-I error budget α",
                 "type": "float", "default": 0.05, "min": 0.001, "max": 0.20},
            ],
        },
        "experiment_analysis": {
            "title": "🔬 Full A/B Readout",
            "description": "Primary metric, segments, causal analysis, and ship recommendation.",
            "needs_experiment": True,
            "fields": [
                {"key": "experiment_name", "label": "Experiment to analyse",
                 "type": "experiment_select", "default": "",
                 "options": experiments},
            ],
        },
        "causal_analysis": {
            "title": "🔗 Causal Analysis",
            "description": "Choose the right causal method for your experiment design.",
            "needs_experiment": True,
            "fields": [
                {"key": "experiment_name", "label": "Experiment",
                 "type": "experiment_select", "default": "",
                 "options": experiments},
                {"key": "method_choice", "label": "Causal method",
                 "type": "select", "default": "1",
                 "options": [
                     "1 — A/B Test Analysis (random assignment)",
                     "2 — Pre-Post Analysis (100% rollout)",
                     "3 — Diff-in-Differences (partial rollout)",
                     "4 — Interrupted Time Series (100% rollout, long pre-period)",
                     "5 — Propensity Score Matching (observational)",
                     "6 — Regression Discontinuity (threshold assignment)",
                     "7 — Synthetic Control (one treated unit)",
                     "8 — ARIMA Counterfactual",
                     "9 — SARIMA (seasonal)",
                     "10 — BSTS / Causal Impact",
                 ],
                 "option_values": ["1","2","3","4","5","6","7","8","9","10"],
                },
            ],
        },
        "simpsons_paradox": {
            "title": "🔀 Simpson's Paradox Detector",
            "description": "Check whether segment-level effects contradict the overall direction.",
            "needs_experiment": True,
            "fields": [
                {"key": "experiment_name", "label": "Experiment",
                 "type": "experiment_select", "default": "",
                 "options": experiments},
            ],
        },
        "roi_tracker": {
            "title": "💰 ROI Tracker",
            "description": "Track incremental revenue post-ship.",
            "needs_experiment": True,
            "fields": [
                {"key": "experiment_name", "label": "Experiment",
                 "type": "experiment_select", "default": "",
                 "options": experiments},
            ],
        },
        "learnings_repository": {
            "title": "🧠 Learnings Repository",
            "description": "Store and retrieve experiment learnings for organizational memory.",
            "needs_experiment": False,
            "fields": [
                {"key": "action", "label": "Action",
                 "type": "select", "default": "1",
                 "options": ["1 — View / search existing learnings", "2 — Store a new learning"],
                 "option_values": ["1", "2"]},
                {"key": "query", "label": "Search query (for viewing)",
                 "type": "text", "default": "conversion",
                 "help": "Keywords to search existing learnings"},
                {"key": "experiment_name", "label": "Experiment name (for storing)",
                 "type": "text", "default": ""},
                {"key": "ship_decision", "label": "Ship decision",
                 "type": "select", "default": "ship",
                 "options": ["ship", "no_ship", "partial_ship"],
                 "option_values": ["ship", "no_ship", "partial_ship"]},
                {"key": "key_learning", "label": "Key learning",
                 "type": "text", "default": ""},
                {"key": "outcome", "label": "Outcome summary",
                 "type": "text", "default": ""},
            ],
        },
        "uplift_modeller": {
            "title": "🚀 Uplift Modeller",
            "description": "Estimate individual-level causal effects for targeting.",
            "needs_experiment": True,
            "fields": [
                {"key": "experiment_name", "label": "Experiment",
                 "type": "experiment_select", "default": "",
                 "options": experiments},
            ],
        },
        "decision_engine": {
            "title": "🎯 Decision Engine",
            "description": "Optimise targeting using uplift scores.",
            "needs_experiment": True,
            "fields": [
                {"key": "experiment_name", "label": "Experiment",
                 "type": "experiment_select", "default": "",
                 "options": experiments},
            ],
        },
    }

    cfg = CONFIGS.get(module_key, {
        "title": module_key.replace("_", " ").title(),
        "description": "Run this module.",
        "needs_experiment": False,
        "fields": [],
    })
    cfg["experiments"] = experiments
    return cfg


# ── execute + SSE stream ──────────────────────────────────────────────────────
@bp.route("/execute/<module_key>", methods=["POST"])
def execute(module_key: str):
    app    = _app()
    run_id = str(uuid.uuid4())[:8]
    q: queue.Queue = queue.Queue()
    app.stream_queues[run_id] = q
    body        = request.get_json(silent=True) or {}
    form_fields = body.get("fields", {})   # user-supplied field values from the config form
    exp         = form_fields.get("experiment_name") or body.get("experiment_name") or app.ses.active_experiment

    def _worker():
        import builtins, sys, io
        from continum.api.dispatcher import run_module, _build_registry, get_module
        _build_registry()

        def is_stopped():
            se = getattr(app, "stop_events", {}).get(run_id)
            return se is not None and se.is_set()

        def emit(level, msg):
            if msg and str(msg).strip():
                q.put(json.dumps({"level": level, "msg": str(msg).rstrip(), "ts": round(time.time(), 3)}))

        # ── Stdout capture → SSE queue ────────────────────────────────────────
        # Every print() in every module will appear in the UI console in real time
        _orig_stdout = sys.stdout
        _buf = []

        class _QueueWriter(io.TextIOBase):
            encoding = getattr(_orig_stdout, "encoding", "utf-8") or "utf-8"
            errors   = "replace"

            def write(self, text):
                if not text:
                    return 0
                _buf.append(str(text))
                combined = "".join(_buf)
                if "\n" in combined:
                    lines = combined.split("\n")
                    for line in lines[:-1]:
                        stripped = line.rstrip()
                        if stripped:
                            emit("OUT", stripped)
                    _buf.clear()
                    if lines[-1]:
                        _buf.append(lines[-1])
                return len(text)

            def flush(self):
                if _buf:
                    remaining = "".join(_buf).rstrip()
                    if remaining:
                        emit("OUT", remaining)
                    _buf.clear()

            def writable(self):   return True
            def readable(self):   return False
            def seekable(self):   return False
            def isatty(self):     return False
            def closed(self):     return False

            def fileno(self):
                try:
                    return _orig_stdout.fileno()
                except Exception:
                    raise io.UnsupportedOperation("fileno")

            def __getattr__(self, name):
                # Proxy any other attribute to the original stdout
                return getattr(_orig_stdout, name)

        sys.stdout = _QueueWriter()

        emit("INFO", f"Starting {module_key}...")
        spec = get_module(module_key)
        if spec is None:
            emit("ERR",  f"Module '{module_key}' not found in registry.")
            emit("DONE", "__done__")
            return

        # Build kwargs: module defaults first, user form input on top (higher priority)
        kw = {}
        kw.update(_build_default_kwargs(module_key, exp, app))
        kw.update(form_fields)   # user's actual input always wins
        # Only inject experiment_name for modules that operate on experiments
        _EXP_MODULES = {
            "health_monitor", "sequential_testing", "experiment_analysis",
            "causal_analysis", "causal_analysis_full", "simpsons_paradox",
            "roi_tracker", "pre_post_analysis", "uplift_modeller",
            "decision_engine", "learnings_repository", "brief_generator",
        }
        if exp and module_key in _EXP_MODULES:
            kw["experiment_name"] = kw.get("experiment_name") or exp
            kw["experiment_id"]   = kw.get("experiment_id")   or exp
        if "method_choice" in kw:
            kw["method_choice"] = str(kw["method_choice"]).split(" ")[0].strip()

        # Build answer_map for input() safety net
        answer_map = _build_answer_map(module_key, kw)

        # Patch input() — thread-local, always restored in finally
        _orig_input = builtins.input
        def _smart_input(prompt=""):
            p = str(prompt).lower()
            for fragment, answer in answer_map.items():
                if fragment and fragment in p:
                    emit("INFO", f"Input: {str(prompt).split('[')[0].strip()} -> {answer}")
                    return str(answer)
            return ""
        builtins.input = _smart_input

        t0 = time.monotonic()
        try:
            emit("INFO", f"Phase: {spec.phase} | Running {module_key}...")
            # ── Check for stop before running ─────────────────────────────────
            if is_stopped():
                emit("WARN", f"⛔ {module_key} cancelled by user before start")
                emit("DONE", "__done__")
                return

            try:
                result = run_module(module_key, state=app.state, llm=app.llm, db=app.db, **kw)
            except TypeError as _te:
                if "unexpected keyword argument" in str(_te):
                    # Strip non-standard kwargs that this module doesn't accept
                    # Strip ALL keys auto-injected by _build_default_kwargs
                    # (only keep what the user explicitly provided in the form)
                    _AUTO_INJECTED = {
                        # DB metrics
                        "baseline_ior", "ior", "current_ior", "aov",
                        "daily_inquiries", "monthly_inquiries",
                        "daily_eligible_traffic",
                        # session/identity
                        "experiment_name", "experiment_id",
                        "session_id", "client_name",
                        # power_calculator defaults
                        "Baseline conversion/IOR rate (0-1)",
                        "MDE — minimum detectable effect (% relative, e.g. 10)",
                        "Significance level α", "Statistical power 1-β",
                        "Number of variants (including control)",
                        "Daily eligible traffic",
                        "Fraction of traffic in experiment (0-1)",
                        # opportunity_sizing defaults
                        "target_ior", "avg_aov", "gross_margin", "horizon",
                        "monthly_inquiries",
                        # other module defaults
                        "category", "experiment_type", "maturity",
                        "action", "query",
                        # generic scheduling/prompt params
                        "select experiment",
                        "method_choice",
                    }
                    _safe_kw = {k: v for k, v in kw.items()
                                if k not in _AUTO_INJECTED}
                    result = run_module(module_key, state=app.state,
                                        llm=app.llm, db=app.db, **_safe_kw)
                else:
                    raise
            elapsed = time.monotonic() - t0

            from continum.runtime.shell.executor import _summarise
            summary = _summarise(result, module_key)
            app.ses.set(f"{module_key}_result", result)
            app.ses.set("experiment_result", result)
            app.ses.record_run(module_key, spec.phase, elapsed, ok=True, summary=summary)
            app.ses.save()

            from continum.runtime.intelligence import publish_next_steps
            publish_next_steps(module_key, app.bus)
            app.bus.success(module_key, f"{module_key} completed in {elapsed:.2f}s  {summary}")
            app.aud.record("module_run", module_key,
                           {"elapsed_s": round(elapsed, 2), "summary": summary, "ok": True},
                           session_id=app.ses.session_id)
            try:
                from continum.runtime.narrative import get_narrative
                nr = get_narrative(bus=app.bus, session=app.ses, memory=app.mem)
                nr.after_module(module_key, result)
            except Exception:
                pass

            # Emit output files as clickable links
            if isinstance(result, dict) and result.get("_outputs"):
                emit("SEP", "─" * 60)
                emit("FILES", f"📁 {len(result['_outputs'])} output file(s) saved:")
                for fpath in result["_outputs"]:
                    import os
                    fname = os.path.basename(fpath)
                    emit("FILE", f"  {fname}||{fpath}")
            emit("SEP",  "─" * 60)
            # Persist file list for /api/outputs/<run_id>
            if isinstance(result, dict) and result.get("_outputs"):
                app.stream_queues[f"files_{run_id}"] = result["_outputs"]
            emit("OK",   f"✅ {module_key} completed in {elapsed:.2f}s")
            if summary:
                emit("SUMMARY", summary)
            emit("DONE", "__done__")

        except Exception as e:
            import traceback
            elapsed = time.monotonic() - t0
            tb_lines = traceback.format_exc().strip().split("\n")
            emit("SEP",  "─" * 60)
            emit("ERR",  f"❌ {type(e).__name__}: {str(e)[:250]}")
            # Show relevant traceback lines
            for tb_line in tb_lines[-6:]:
                stripped = tb_line.strip()
                if stripped and not stripped.startswith("Traceback"):
                    emit("ERR", f"  {stripped[:180]}")
            emit("SEP",  "─" * 60)
            emit("ERR",  f"Module failed after {elapsed:.2f}s")
            emit("DONE", "__done__")
            app.ses.record_run(module_key, getattr(spec, "phase", "?"),
                               elapsed, ok=False, error=str(e))
            app.ses.save()
            app.aud.record("module_run", module_key, {"error": str(e), "ok": False},
                           ok=False, session_id=app.ses.session_id)
            logger.exception("Execute %s failed", module_key)
        finally:
            builtins.input = _orig_input
            # Always restore stdout and flush remaining buffer
            try:
                sys.stdout.flush()
            except Exception:
                pass
            sys.stdout = _orig_stdout
    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"run_id": run_id})


@bp.route("/outputs/<run_id>")
def list_run_outputs(run_id: str):
    app   = _app()
    files = app.stream_queues.get(f"files_{run_id}", [])
    out   = []
    for fpath in files:
        import os
        if os.path.exists(fpath):
            fname = os.path.basename(fpath)
            out.append({"name": fname, "path": fpath,
                        "url":  f"/api/file?path={fpath}",
                        "size": os.path.getsize(fpath)})
    return jsonify(out)


@bp.route("/file")
def serve_file():
    import os
    from flask import send_file as _sf, abort
    fpath = request.args.get("path", "")
    if not fpath or not os.path.exists(fpath):
        return abort(404)
    # Security: only serve from continum output directories
    import os as _os
    _home_out = _os.path.join(_os.path.expanduser("~"), "continum_outputs")
    _allowed  = ["/tmp/continum_outputs", _home_out,
                 _os.environ.get("CONTINUM_OUTPUT_DIR", "")]
    if not any(fpath.startswith(a) for a in _allowed if a):
        return abort(403)
    return _sf(fpath, as_attachment=False)


def _build_default_kwargs(module_key: str, exp: str, app) -> dict:
    kw: dict = {}
    # Experiment / session defaults
    if exp:
        kw["experiment_name"] = exp
        kw["experiment_id"]   = exp

    # Pull live baselines from DB
    db = getattr(app, "db", None)
    if db is not None:
        try:
            row = db.execute("""
                SELECT AVG(CAST(converted_to_order AS DOUBLE)) AS ior,
                       AVG(CASE WHEN converted_to_order THEN order_value END) AS aov,
                       COUNT(*) / NULLIF(DATEDIFF('day',MIN(created_at),MAX(created_at))+1,0) AS daily_n
                FROM silver_inquiries WHERE converted_to_order IS NOT NULL
            """).fetchone()
            if row and row[0]:
                kw.update({
                    "baseline_ior":          float(row[0] or 0.18),
                    "ior":                   float(row[0] or 0.18),
                    "current_ior":           float(row[0] or 0.18),
                    "aov":                   float(row[1] or 4000),
                    "daily_inquiries":       float(row[2] or 500),
                    "monthly_inquiries":     float(row[2] or 500) * 30.4,
                    "daily_eligible_traffic": float(row[2] or 500),
                })
        except Exception:
            kw.setdefault("baseline_ior", 0.18)
            kw.setdefault("ior",          0.18)
            kw.setdefault("aov",          4000.0)
            kw.setdefault("daily_inquiries", 500.0)

    # Session-level defaults
    ses = getattr(app, "ses", None)
    if ses is not None:
        kw.setdefault("session_id", getattr(ses, "session_id", "default"))
        kw.setdefault("client_name", getattr(ses, "client_name", "demo"))

    # Module-specific defaults
    defaults_map = {
        "power_calculator": {
            "Baseline conversion/IOR rate (0-1)":              kw.get("baseline_ior", 0.18),
            "MDE — minimum detectable effect (% relative, e.g. 10)": 10.0,
            "Significance level α":                            0.05,
            "Statistical power 1-β":                          0.80,
            "Number of variants (including control)":          2,
            "Daily eligible traffic":                          kw.get("daily_inquiries", 500),
            "Fraction of traffic in experiment (0-1)":         1.0,
        },
        "opportunity_sizing": {
            "monthly_inquiries": kw.get("monthly_inquiries", 15000),
            "current_ior":       kw.get("ior", 0.18),
            "target_ior":        min(kw.get("ior", 0.18) * 1.10, 0.999),
            "avg_aov":           kw.get("aov", 4000),
            "gross_margin":      0.30,
            "horizon":           12,
        },
        "health_monitor":      {"select experiment": "1"},
        "sequential_testing":  {"select experiment": "1"},
        "causal_analysis":     {"method_choice": "1"},
        "audience_selection":  {"category": "conversion"},
        "brief_generator":     {
            "description":    "Checkout funnel optimisation",
            "method":         "ab_test",
            "hypothesis":     "Reducing friction will increase IOR",
            "target_audience":"Active buyers",
        },
        "metrics_and_tracking": {
            "experiment_type": "conversion",
            "maturity":        "mvp",
        },
        "learnings_repository": {
            "action":          "1",
            "query":           exp or "conversion",
        },
    }
    kw.update(defaults_map.get(module_key, {}))
    return kw


def _build_answer_map(module_key: str, kw: dict) -> dict:
    m = {}
    for k, v in kw.items():
        m[k.lower()] = str(v)

    # Module-specific fragments that cover the exact prompt strings
    if module_key == "power_calculator":
        if "baseline conversion/ior rate (0" in "".join(m): pass  # already mapped by key
        # Add common variants
        m.update({
            "baseline conversion": str(kw.get("Baseline conversion/IOR rate (0–1)", kw.get("baseline_ior", 0.18))),
            "minimum detectable effect": str(kw.get("MDE — minimum detectable effect (% relative, e.g. 10)", kw.get("mde_pct", 10.0))),
            "significance level": str(kw.get("Significance level α", kw.get("alpha", 0.05))),
            "statistical power": str(kw.get("Statistical power 1-β", kw.get("power_val", 0.80))),
            "number of variants": str(kw.get("Number of variants (including control)", kw.get("n_variants", 2))),
            "daily eligible traffic": str(kw.get("Daily eligible traffic", kw.get("daily_users", 500))),
            "fraction of traffic": str(kw.get("Fraction of traffic in experiment (0–1)", kw.get("traffic_share", 1.0))),
        })
    elif module_key == "opportunity_sizing":
        m.update({
            "monthly inquiries": str(kw.get("monthly_inquiries", 10000)),
            "current ior": str(kw.get("current_ior_(0–1)", 0.18)),
            "target ior": str(kw.get("target_ior_after_experiment_(0–1)", 0.198)),
            "average order value": str(kw.get("average_order_value_($)", 500)),
            "gross margin": str(kw.get("gross_margin_(0–1)", 0.30)),
            "time horizon": str(kw.get("time_horizon_(months)", 12)),
        })
    elif module_key == "audience_selection":
        cat_map = {"conversion": "1", "acquisition": "2", "retention": "3", "engagement": "4"}
        cat = kw.get("category", "conversion")
        m["experiment category"] = cat_map.get(cat, "1")
    elif module_key == "causal_analysis":
        m["choose method"] = str(kw.get("method_choice", "1"))
        m["experiment name"] = str(kw.get("experiment_name", ""))
    elif module_key == "metrics_and_tracking":
        m["maturity [mvp"] = str(kw.get("maturity", "mvp"))
    elif module_key == "health_monitor":
        m["select experiment"] = "1"
    elif module_key == "sequential_testing":
        m["select experiment"] = "1"
    elif module_key == "learnings_repository":
        m["choose [1/2/3]"]  = str(kw.get("action", "1"))
        m["search query"]    = str(kw.get("query", "conversion"))
        m["experiment name"] = str(kw.get("experiment_name", ""))
        m["ship decision"]   = str(kw.get("ship_decision", "ship"))
        m["key learning"]    = str(kw.get("key_learning", "Stored from UI"))
        m["outcome summary"] = str(kw.get("outcome", "Completed via UI"))
        m["what worked"]     = str(kw.get("what_worked", "Treatment variant"))
        m["what did not"]    = "N/A"
        m["recommendation"]  = str(kw.get("recommendation", "Review analysis"))
        m["follow-up ideas"] = ""
        m["tags"]            = "ui"
    elif module_key == "schema_discovery":
        m["client / project name"] = str(kw.get("client_name", "demo"))
        m["client_name"]           = str(kw.get("client_name", "demo"))
    return m


@bp.route("/stream/<run_id>")
def stream(run_id: str):
    app = _app()
    q   = app.stream_queues.get(run_id)
    if q is None:
        return Response('data: {"level":"ERR","msg":"unknown run_id"}\n\n',
                        mimetype="text/event-stream")

    from flask import stream_with_context

    def _gen():
        while True:
            try:
                msg  = q.get(timeout=30)
                # Always yield bytes — required by Werkzeug on Windows
                yield (f"data: {msg}\n\n").encode("utf-8")
                try:
                    data = json.loads(msg)
                    if data.get("msg") == "__done__":
                        app.stream_queues.pop(run_id, None)
                        break
                except Exception:
                    pass
            except queue.Empty:
                yield b'data: {"level":"PING","msg":"..."}\n\n'

    return Response(
        _gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":    "no-cache, no-transform",
            "X-Accel-Buffering":"no",
            "Connection":       "keep-alive",
            "Content-Type":     "text/event-stream; charset=utf-8",
        },
        direct_passthrough=True,
    )


# ── session ───────────────────────────────────────────────────────────────────
@bp.route("/session")
def session_state():
    app = _app()
    s   = app.ses
    return jsonify({
        "session_id":       s.session_id,
        "client_name":      s.client_name,
        "active_experiment":s.active_experiment,
        "active_metrics":   s.active_metrics,
        "n_runs":           len(s.execution_history),
        "history": [{"module": r.module, "ok": r.ok,
                     "elapsed": round(r.elapsed_s, 2),
                     "summary": r.summary, "phase": r.phase}
                    for r in s.execution_history[-20:]],
        "recommendations": [{"action": r.action, "reason": r.reason,
                              "priority": r.priority}
                             for r in s.recommendations[:5]],
        "context_keys": list(s._context.keys()),
    })


@bp.route("/session/fork", methods=["POST"])
def fork_session():
    app  = _app()
    label = (request.get_json(silent=True) or {}).get("label", "")
    fork = app.ses.fork(label=label or None)
    # Switch the app to the fork
    app.ses = fork
    fork.db = app.db; fork.state = app.state
    app.aud.record("session_fork", fork.session_id,
                   {"parent": fork._parent_id, "label": label})
    return jsonify({"ok": True, "session_id": fork.session_id,
                    "description": getattr(fork, "fork_description", "")})


@bp.route("/session/snapshot", methods=["POST"])
def snapshot():
    app   = _app()
    label = (request.get_json(silent=True) or {}).get("label", "")
    sid   = app.snap.take(app.ses, bus=app.bus, label=label)
    app.aud.record("snapshot", sid, {"label": label}, session_id=app.ses.session_id)
    return jsonify({"ok": True, "snapshot_id": sid})


@bp.route("/session/snapshots")
def list_snapshots():
    return jsonify(_app().snap.list_snapshots())


# ── intelligence ──────────────────────────────────────────────────────────────
@bp.route("/intelligence")
def intelligence():
    app = _app()
    bus = app.bus

    def _d(i):
        return {"type": i.insight_type, "severity": i.severity,
                "source": i.source_module, "message": i.message, "detail": i.detail}

    return jsonify({
        "insights":       [_d(i) for i in bus.all()[-30:]],
        "warnings":       [_d(i) for i in bus.warnings()],
        "recommendations":[_d(i) for i in bus.recommendations()],
        "kpis":           [_d(i) for i in bus.kpi_suggestions()],
    })


# ── inspect ───────────────────────────────────────────────────────────────────
@bp.route("/inspect/<what>")
def inspect_endpoint(what: str):
    app = _app()
    from continum.runtime.inspect import inspect
    report = inspect(what, session=app.ses, db=app.db, bus=app.bus, memory=app.mem)
    return jsonify(report)


@bp.route("/inspect")
def inspect_all():
    app = _app()
    from continum.runtime.inspect import inspect_all
    return jsonify(inspect_all(session=app.ses, db=app.db, bus=app.bus, memory=app.mem))


# ── ask ───────────────────────────────────────────────────────────────────────
@bp.route("/ask", methods=["POST"])
def ask():
    app  = _app()
    body = request.get_json(silent=True) or {}
    q    = body.get("question", "").strip()
    if not q:
        return jsonify({"error": "No question"}), 400

    from continum.runtime.ask import ContinumCopilot
    # Use a persistent copilot stored on the app for multi-turn
    if not hasattr(app, "_copilot"):
        app._copilot = ContinumCopilot(
            session=app.ses, bus=app.bus, memory=app.mem, db=app.db)
    app._copilot.session = app.ses  # keep in sync with fork switches
    response = app._copilot.ask(q)
    app.aud.record("ask", q[:60], {"intent": "ask"}, session_id=app.ses.session_id)
    return jsonify({"question": q, "response": response})


# ── compare ───────────────────────────────────────────────────────────────────
@bp.route("/compare", methods=["POST"])
def compare():
    app  = _app()
    body = request.get_json(silent=True) or {}
    a    = body.get("experiment_a", "").strip()
    b    = body.get("experiment_b", "").strip()
    if not a or not b:
        return jsonify({"error": "Provide experiment_a and experiment_b"}), 400
    if not app.db:
        return jsonify({"error": "No database connected"}), 503

    from continum.runtime.compare import _extract_metrics, _synthesise
    from continum.api.dispatcher  import run_module, _build_registry
    _build_registry()
    results = {}
    for name in [a, b]:
        try:
            r = run_module("experiment_analysis", state=app.state, llm=app.llm,
                           db=app.db, experiment_name=name, experiment_id=name)
            results[name] = r
            if r:
                app.mem.record_experiment(name, name, r)
        except Exception as e:
            results[name] = None
            logger.debug("compare %s: %s", name, e)

    ma = _extract_metrics(results.get(a))
    mb = _extract_metrics(results.get(b))

    def _s(m):
        return {k: v for k, v in m.items() if k not in ("slices", "guardrails")}

    return jsonify({
        "experiment_a": {"name": a, "metrics": _s(ma)},
        "experiment_b": {"name": b, "metrics": _s(mb)},
        "narrative":    _synthesise(a, ma, b, mb),
    })


# ── lineage ───────────────────────────────────────────────────────────────────
@bp.route("/lineage")
def lineage():
    app = _app()
    from continum.runtime.inspect import inspect
    return jsonify(inspect("lineage", session=app.ses, db=app.db))


# ── audit ─────────────────────────────────────────────────────────────────────
@bp.route("/llm/status")
def llm_status_endpoint():
    from continum.core.llm.manager import llm_status
    return jsonify(llm_status())


@bp.route("/llm/load", methods=["POST"])
def llm_load():
    import threading
    app = _app()

    def _load():
        try:
            from continum.core.llm.manager import load_llm
            app.llm = load_llm()
            app.bus.success("llm", f"Qwen2.5-1.5B-Instruct loaded on {app.llm._device}")
            app.aud.record("llm_load", "Qwen2.5-1.5B-Instruct",
                           {"device": app.llm._device}, session_id=app.ses.session_id)
        except Exception as e:
            app.bus.warn("llm", f"LLM load failed: {str(e)[:120]}")
            logger.exception("LLM load failed")

    threading.Thread(target=_load, daemon=True).start()
    return jsonify({"ok": True, "message": "Model loading in background — check /api/llm/status"})


@bp.route("/llm/unload", methods=["POST"])
def llm_unload():
    app = _app()
    from continum.core.llm.manager import unload_llm
    unload_llm()
    app.llm = None
    return jsonify({"ok": True, "message": "Model unloaded"})


@bp.route("/ask/chain", methods=["POST"])
def ask_chain():
    app  = _app()
    body = request.get_json(silent=True) or {}
    q    = body.get("question", "").strip()
    if not q:
        return jsonify({"error": "No question provided"}), 400

    # ── Step 1: Pull live data from DB (always, regardless of LLM) ────────────
    db_facts = {}
    if app.db:
        # Discover the actual outcome column name (schema may vary)
        _outcome_col = "converted_to_order"
        _value_col   = "order_value"
        _seg_col     = "account_segment"
        try:
            cols = [r[0].lower() for r in app.db.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'silver_inquiries'"
            ).fetchall()]
            if cols:
                # Find outcome column
                for candidate in ("converted_to_order","is_converted","conversion","ordered",
                                   "converted","is_order","order_flag"):
                    if candidate in cols:
                        _outcome_col = candidate; break
                # Find value column
                for candidate in ("order_value","aov","order_total","revenue","amount",
                                   "order_amount","gmv"):
                    if candidate in cols:
                        _value_col = candidate; break
                # Find segment column
                for candidate in ("account_segment","segment","customer_segment","tier",
                                   "customer_tier","user_segment"):
                    if candidate in cols:
                        _seg_col = candidate; break
        except Exception:
            pass

        try:
            row = app.db.execute(f"""
                SELECT AVG(CAST({_outcome_col} AS DOUBLE)) AS ior,
                       AVG(CASE WHEN {_outcome_col} THEN {_value_col} END) AS aov,
                       COUNT(*) AS n,
                       STDDEV(CAST({_outcome_col} AS DOUBLE)) AS ior_std
                FROM silver_inquiries WHERE {_outcome_col} IS NOT NULL
            """).fetchone()
            if row and row[0]:
                db_facts["ior"]     = round(float(row[0]), 4)
                db_facts["aov"]     = round(float(row[1] or 0), 2)
                db_facts["n"]       = int(row[2])
                db_facts["ior_std"] = round(float(row[3] or 0), 4)
        except Exception as e:
            logger.debug("ask_chain: metrics query failed: %s", e)

        try:
            rows = app.db.execute(f"""
                SELECT {_seg_col},
                       AVG(CAST({_outcome_col} AS DOUBLE)) AS ior,
                       COUNT(*) AS n
                FROM silver_inquiries WHERE {_seg_col} IS NOT NULL
                GROUP BY {_seg_col} ORDER BY ior DESC
            """).fetchall()
            db_facts["segments"] = {
                str(r[0]): {"ior": round(float(r[1]),4), "n": int(r[2])} for r in rows
            }
        except Exception:
            pass

        try:
            exp_rows = app.db.execute(f"""
                SELECT experiment_name, variant,
                       COUNT(*) AS n,
                       AVG(CAST({_outcome_col} AS DOUBLE)) AS ior
                FROM gold_experiment_analysis
                WHERE experiment_name IS NOT NULL
                GROUP BY experiment_name, variant
                ORDER BY experiment_name, variant
            """).fetchall()
            exp_data = {}
            for r in exp_rows:
                en = str(r[0])
                if en not in exp_data:
                    exp_data[en] = {}
                exp_data[en][str(r[1])] = {"n": int(r[2]), "ior": round(float(r[3]),4)}
            db_facts["experiments"] = exp_data
        except Exception:
            pass

        try:
            row = app.db.execute(f"""
                SELECT AVG(CAST({_outcome_col} AS DOUBLE))
                FROM silver_inquiries
                WHERE created_at >= CURRENT_DATE - INTERVAL 1 DAY
            """).fetchone()
            if row and row[0]:
                db_facts["ior_24h"] = round(float(row[0]), 4)
        except Exception:
            pass

    # ── Step 2: Session context ────────────────────────────────────────────────
    session_facts = {}
    if app.ses:
        session_facts["active_experiment"] = app.ses.active_experiment or "none"
        session_facts["modules_run"] = [
                            (h.get("module","") if isinstance(h, dict)
                             else getattr(h, "module", getattr(h, "module_key", "")))
                            for h in (app.ses.execution_history or [])[-8:]
                        ]
        exp_result = app.ses.get("experiment_result")
        if isinstance(exp_result, dict) and exp_result.get("primary"):
            primary = exp_result["primary"]
            best = max(primary, key=lambda k: primary[k].get("delta_pp", 0), default="")
            if best:
                session_facts["last_result"] = {
                    "treatment": best,
                    "delta_pp": primary[best].get("delta_pp", 0),
                    "p_value":  primary[best].get("p_value", 1),
                    "sig":      primary[best].get("sig", False),
                    "decision": exp_result.get("decision", "unknown"),
                }

    # ── Step 3: Recent bus insights ────────────────────────────────────────────
    recent_insights = []
    if app.bus:
        try:
            for ins in (app.bus.recent(5) or []):
                recent_insights.append(f"{ins.source_module}: {ins.message}")
        except Exception:
            pass

    # ── Step 4: Build evidence chain (always deterministic) ───────────────────
    q_lower = q.lower()
    evidence = []
    response_parts = []

    # IOR / conversion questions
    if any(t in q_lower for t in ["ior","conversion","convert","rate"]):
        if "ior" in db_facts:
            evidence.append({"source":"live_db","claim":f"Overall IOR = {db_facts['ior']*100:.3f}%  (n={db_facts['n']:,})","confidence":0.95,"valence":"supports"})
            response_parts.append(f"Current IOR: **{db_facts['ior']*100:.3f}%** across {db_facts['n']:,} inquiries.")
        if "segments" in db_facts:
            best_seg = max(db_facts["segments"], key=lambda k: db_facts["segments"][k]["ior"])
            worst_seg = min(db_facts["segments"], key=lambda k: db_facts["segments"][k]["ior"])
            evidence.append({"source":"segments","claim":f"Best: {best_seg} ({db_facts['segments'][best_seg]['ior']*100:.2f}%)  Worst: {worst_seg} ({db_facts['segments'][worst_seg]['ior']*100:.2f}%)","confidence":0.90,"valence":"supports"})
            response_parts.append(f"Best segment: {best_seg} ({db_facts['segments'][best_seg]['ior']*100:.2f}%). Worst: {worst_seg} ({db_facts['segments'][worst_seg]['ior']*100:.2f}%).")

    # Anomaly / drop / spike
    if any(t in q_lower for t in ["drop","fall","declin","anomal","spike","spike","issue","wrong"]):
        if "ior_24h" in db_facts and "ior" in db_facts:
            delta = (db_facts["ior_24h"] - db_facts["ior"]) * 100
            std   = db_facts.get("ior_std", db_facts["ior"] * 0.05)
            z     = delta / (std * 100) if std > 0 else 0
            sev   = "🚨 critical" if abs(z) > 3 else "⚠️ warning" if abs(z) > 2 else "✅ normal"
            evidence.append({"source":"anomaly_check","claim":f"24h IOR={db_facts['ior_24h']*100:.3f}% vs baseline {db_facts['ior']*100:.3f}% (z={z:+.2f}, {sev})","confidence":0.85,"valence":"contradicts" if abs(z)>2 else "supports"})
            if abs(z) > 2:
                response_parts.append(f"{'🚨' if abs(z)>3 else '⚠️'} Anomaly detected: 24h IOR = {db_facts['ior_24h']*100:.3f}% vs baseline {db_facts['ior']*100:.3f}% (z={z:+.2f}).")
                response_parts.append("Possible causes: SRM in active experiment, data pipeline issue, or genuine traffic mix shift. Run Health Monitor to investigate.")
            else:
                response_parts.append(f"No anomaly: 24h IOR ({db_facts['ior_24h']*100:.3f}%) is within normal range of baseline ({db_facts['ior']*100:.3f}%).")

    # Experiment results
    if any(t in q_lower for t in ["experiment","test","result","significant","ship","work","treatment"]):
        active_exp = session_facts.get("active_experiment","")
        if "experiments" in db_facts and active_exp and active_exp in db_facts["experiments"]:
            exp = db_facts["experiments"][active_exp]
            ctrl  = exp.get("control", list(exp.values())[0] if exp else {})
            trt_keys = [k for k in exp if k != "control"]
            if trt_keys:
                trt = exp[trt_keys[0]]
                delta_pp = (trt["ior"] - ctrl["ior"]) * 100
                evidence.append({"source":"experiment_data","claim":f"{active_exp}: Δ={delta_pp:+.3f}pp  ctrl={ctrl['ior']*100:.3f}%  trt={trt['ior']*100:.3f}%  n={ctrl['n']+trt['n']:,}","confidence":0.90,"valence":"supports" if delta_pp>0 else "contradicts"})
                response_parts.append(f"Experiment **{active_exp}**: treatment={trt_keys[0]} Δ={delta_pp:+.3f}pp (ctrl={ctrl['ior']*100:.3f}%, trt={trt['ior']*100:.3f}%, n={ctrl['n']+trt['n']:,}).")
        if session_facts.get("last_result"):
            r = session_facts["last_result"]
            evidence.append({"source":"last_analysis","claim":f"Last analysis: {r['treatment']} Δ={r['delta_pp']:+.3f}pp p={r['p_value']:.4f} {'✅ sig' if r['sig'] else '⏳ n.s.'} → {r['decision']}","confidence":0.95,"valence":"supports" if r["delta_pp"]>0 else "contradicts"})
            response_parts.append(f"Last analysis: {r['treatment']} Δ={r['delta_pp']:+.3f}pp, p={r['p_value']:.4f} {'(significant)' if r['sig'] else '(not significant)'} → decision: **{r['decision']}**.")

    # Next step / recommendation
    if any(t in q_lower for t in ["next","should","recommend","what to do","what do","suggest","run"]):
        modules_run = set(session_facts.get("modules_run",[]))
        chain = [
            ("power_calculator",   "power_calculator" not in modules_run,   "Run Power Calculator to size the required sample."),
            ("health_monitor",     "health_monitor" not in modules_run,      "Run Health Monitor to check SRM and guardrails."),
            ("experiment_analysis","experiment_analysis" not in modules_run, "Run Experiment Analysis for the full statistical readout."),
            ("causal_analysis",    "causal_analysis" not in modules_run,     "Run Causal Analysis (DiD/ITS/PSM) to strengthen attribution."),
            ("roi_tracker",        "roi_tracker" not in modules_run,         "Run ROI Tracker to measure post-ship incremental GMV."),
        ]
        pending = [(m, r) for m, cond, r in chain if cond]
        if pending:
            evidence.append({"source":"session_state","claim":f"Pending: {', '.join(m for m,_ in pending[:3])}","confidence":0.80,"valence":"supports"})
            response_parts.append("Recommended next steps:")
            for i, (m, r) in enumerate(pending[:3], 1):
                response_parts.append(f"  {i}. **{m}**: {r}")
        else:
            response_parts.append("All core modules have run. Consider Uplift Modeller for targeted rollout or Decision Engine for ship recommendation.")

    # Segment question
    if any(t in q_lower for t in ["segment","core","growth","enterprise","individual","platform","mobile","web"]):
        if "segments" in db_facts:
            lines = [f"  {seg}: IOR={v['ior']*100:.2f}%  (n={v['n']:,})" for seg,v in db_facts["segments"].items()]
            evidence.append({"source":"segment_data","claim":"\n".join(lines),"confidence":0.95,"valence":"supports"})
            response_parts.append("Segment IOR breakdown:")
            for seg, v in db_facts["segments"].items():
                bar = "█" * int(v["ior"]*100/3)
                response_parts.append(f"  {seg:<18} {v['ior']*100:.2f}%  {bar}")

    # Recent insights from bus
    if any(t in q_lower for t in ["insight","alert","warning","anomal","guardrail"]):
        if recent_insights:
            evidence.append({"source":"insight_bus","claim":"\n".join(recent_insights),"confidence":0.75,"valence":"supports"})
            response_parts.append("Recent system insights:")
            for ins in recent_insights[:4]:
                response_parts.append(f"  • {ins}")

    # Fallback if nothing matched
    if not response_parts:
        if db_facts.get("ior"):
            response_parts.append(f"Current state: IOR={db_facts['ior']*100:.3f}%  AOV=${db_facts.get('aov',0):,.0f}  n={db_facts.get('n',0):,}")
        if session_facts.get("active_experiment"):
            response_parts.append(f"Active experiment: {session_facts['active_experiment']}")
        if session_facts.get("modules_run"):
            response_parts.append(f"Modules run: {', '.join(session_facts['modules_run'][-4:])}")
        response_parts.append("Ask me about: IOR trends, experiment results, anomalies, segment breakdowns, what to run next.")

    det_response = "\n".join(response_parts)

    # ── Step 5: LLM narrative (grounded, only if loaded) ──────────────────────
    llm_response = None
    llm_loaded   = bool(app.llm and hasattr(app.llm, "is_loaded") and app.llm.is_loaded)
    if not llm_loaded and app.llm is not None:
        # Check via the manager
        try:
            from continum.core.llm.manager import llm_status
            llm_loaded = llm_status().get("is_loaded", False)
        except Exception:
            pass

    if llm_loaded:
        # 1. Extract and format the segments cleanly first
        top_segments = list(db_facts.get('segments', {}).items())[:4]
        segments_list = [f"{k}={v['ior']*100:.2f}%" for k, v in top_segments]
        segments_str = f"Segments: {', '.join(segments_list)}"

        # 2. Build your final string smoothly
        try:
            facts_str = "\n".join([
                f"IOR: {db_facts.get('ior',0)*100:.3f}%  AOV: ${db_facts.get('aov',0):,.0f}  n: {db_facts.get('n',0):,}",
                segments_str,
                f"Active experiment: {session_facts.get('active_experiment','none')}",
            ])
            prompt = (
                f"Analytics AI. Answer from live data only. Be direct and specific.\n"
                f"Q: {q}\n\n"
                f"Data: {facts_str}\n\n"
                f"Findings: {det_response[:400]}\n\n"
                f"2-3 sentences. Reference numbers. No preamble."
            )
            # Run LLM in thread with 15s timeout to prevent hanging
            import threading as _thr
            _llm_result = [None]
            def _llm_call():
                try:
                    _llm_result[0] = str(app.llm.ask(prompt))
                except Exception as _e:
                    logger.debug("LLM ask thread: %s", _e)
            _t = _thr.Thread(target=_llm_call, daemon=True)
            _t.start()
            _t.join(timeout=15)
            if _llm_result[0]:
                llm_response = _llm_result[0]
        except Exception as e:
            logger.debug("LLM ask failed: %s", e)

    final_response = llm_response if llm_response else det_response

    # Synthesis line for the evidence chain
    synthesis = final_response.split("\n")[0] if final_response else ""

    try:
        app.aud.record("ask_chain", q[:60], {
            "intent": "grounded_ask", "llm_used": bool(llm_response),
            "n_evidence": len(evidence),
        }, session_id=app.ses.session_id if app.ses else "")
    except Exception:
        pass

    # Sanitize all values for JSON serialization (numpy types, etc.)
    def _safe(v):
        if isinstance(v, (bool, int, float, str, type(None))):
            return v
        try:
            import numpy as np
            if isinstance(v, np.integer): return int(v)
            if isinstance(v, np.floating): return float(v)
            if isinstance(v, np.ndarray): return v.tolist()
        except ImportError:
            pass
        return str(v)

    clean_evidence = []
    for ev in evidence:
        try:
            clean_evidence.append({
                "source":     str(ev.get("source", "")),
                "claim":      str(ev.get("claim", ""))[:400],
                "confidence": float(ev.get("confidence", 0.5)),
                "valence":    str(ev.get("valence", "supports")),
            })
        except Exception:
            pass

    try:
        return jsonify({
            "question": str(q),
            "response": str(final_response),
            "chain": {
                "evidence":  clean_evidence,
                "synthesis": str(synthesis)[:300],
            },
            "intent":     "grounded_ask",
            "entities":   {},
            "llm_used":   bool(llm_response),
            "llm_loaded": bool(llm_loaded),
        })
    except Exception as _je:
        logger.error("ask_chain jsonify failed: %s", _je)
        return jsonify({
            "question": str(q),
            "response": str(final_response)[:2000],
            "chain":    {"evidence": [], "synthesis": ""},
            "intent":   "grounded_ask",
            "llm_used": False,
            "error":    str(_je),
        })



def _build_llm_session_context(session, bus, memory) -> str:
    lines = []

    lines.append(f"Session: {session.session_id} | Client: {session.client_name}")
    lines.append(f"Active experiment: {session.active_experiment or 'none selected'}")
    lines.append(f"Active metrics: {', '.join(session.active_metrics) or 'none'}")

    # Experiment result
    result = session.get("experiment_result")
    if result:
        try:
            def _g(o, *ks, d=None):
                for k in ks:
                    v = getattr(o, k, None) or (o.get(k) if isinstance(o, dict) else None)
                    if v is not None:
                        return v
                return d
            r       = _g(result, "result") or result
            primary = _g(r, "primary_delta")
            if primary:
                lines.append(
                    f"\nPrimary metric result:"
                    f"\n  Δ = {float(_g(primary, 'delta_pp', d=0)):+.4f}pp"
                    f"  p = {float(_g(primary, 'p_value', d=1)):.4f}"
                    f"  significant = {bool(_g(primary, 'is_significant', d=False))}"
                    f"\n  n_control = {int(_g(primary, 'n_control', d=0)):,}"
                    f"  n_treatment = {int(_g(primary, 'n_treatment', d=0)):,}"
                )
            verdict = _g(r, "verdict")
            ship    = _g(r, "ship_recommendation")
            srm     = _g(r, "srm_detected", d=False)
            if verdict:
                lines.append(f"  Verdict: {verdict}  |  Ship: {ship}  |  SRM: {srm}")

            # Segment findings (top 5 most impactful)
            slices = _g(r, "slice_findings", d=[]) or []
            if slices:
                lines.append(f"\nSegment findings ({len(slices)} total, showing top 5):")
                sorted_slices = sorted(
                    slices,
                    key=lambda s: abs(float(getattr(getattr(s, "delta", s), "delta_pp", 0) or 0)),
                    reverse=True
                )[:5]
                for s in sorted_slices:
                    d   = getattr(s, "delta", None) or s
                    dp  = float(getattr(d, "delta_pp", 0) or 0)
                    pv  = float(getattr(d, "p_value", 1) or 1)
                    sig = "sig" if getattr(d, "is_significant", False) else "n.s."
                    dim = getattr(s, "dimension_name", "")
                    val = getattr(s, "dimension_value", "")
                    spx = " [Simpson's paradox]" if getattr(s, "simpsons_paradox_flag", False) else ""
                    lines.append(f"  {dim}={val}: Δ={dp:+.3f}pp p={pv:.4f} {sig}{spx}")
        except Exception as e:
            lines.append(f"(Could not extract result details: {e})")

    # Causal estimates
    causal = session.get("causal_analysis_result")
    if causal:
        estimates = getattr(causal, "estimates", None) or (causal.get("estimates") if isinstance(causal, dict) else []) or []
        if estimates:
            lines.append(f"\nCausal estimates ({len(estimates)} methods):")
            for e in estimates[:4]:
                m   = getattr(e, "method", "?")
                est = float(getattr(e, "estimate", 0) or 0)
                pv  = float(getattr(e, "p_value", 1) or 1)
                sig = "sig" if getattr(e, "is_significant", False) else "n.s."
                lines.append(f"  [{m}]: estimate={est:+.4f}  p={pv:.4f}  {sig}")

    # Run history
    if session.execution_history:
        lines.append(f"\nModules run this session ({len(session.execution_history)}):")
        for r in session.execution_history[-6:]:
            lines.append(f"  {r.module} ({r.elapsed_s:.1f}s) {'✓' if r.ok else '✗'}: {r.summary[:60]}")

    # Warnings
    if bus:
        warnings_list = bus.warnings()
        if warnings_list:
            lines.append(f"\nActive warnings ({len(warnings_list)}):")
            for w in warnings_list[-3:]:
                lines.append(f"  [{w.source_module}] {w.message}")

    # Memory
    if memory:
        n = memory.experiment_count()
        if n:
            lines.append(f"\nCross-experiment memory: {n} experiments stored")
            good = memory.get_successful_metrics(limit=3)
            if good:
                lines.append("Most effective metrics historically:")
                for m in good:
                    lines.append(f"  {m['metric_name']}: {m['sig_rate']:.0%} sig rate ({m['n_experiments']} exps)")

    return "\n".join(lines)


@bp.route("/narrative")
def narrative():
    app = _app()
    from continum.runtime.narrative import get_narrative
    nr = get_narrative(bus=app.bus, session=app.ses, memory=app.mem)

    stream = nr.get_stream(n=15)
    # If stream is thin, inject a fresh thought
    if len(stream) < 3:
        thought = nr.idle_thought()
        if thought:
            stream.insert(0, {
                "text":       thought,
                "source":     "observation",
                "created_at": __import__("datetime").datetime.utcnow().isoformat()[:19],
            })
    return jsonify(stream)


@bp.route("/patterns")
def patterns():
    app = _app()
    from continum.runtime.patterns import get_miner
    miner   = get_miner(app.mem)
    report  = miner.mine_all()
    # Also attach prior for active experiment
    exp = app.ses.active_experiment
    if exp:
        report["prior"] = miner.get_prior(exp).to_dict()
    return jsonify(report)


@bp.route("/audit")
def audit():
    n = int(request.args.get("n", 50))
    return jsonify(_app().aud.tail(n))


# ── governance ────────────────────────────────────────────────────────────────
@bp.route("/governance/request-ship", methods=["POST"])
def request_ship():
    app  = _app()
    body = request.get_json(silent=True) or {}
    exp  = body.get("experiment_id") or app.ses.active_experiment
    if not exp:
        return jsonify({"error": "No experiment_id"}), 400
    approval = app.gov.request_ship(exp, requested_by=body.get("analyst", "analyst"))
    return jsonify(approval.to_dict())


@bp.route("/governance/approve", methods=["POST"])
def approve_ship():
    app  = _app()
    body = request.get_json(silent=True) or {}
    exp  = body.get("experiment_id", "")
    a    = app.gov.approve_ship(exp, reviewed_by=body.get("reviewer", "reviewer"),
                                comment=body.get("comment", ""))
    return jsonify(a.to_dict() if a else {"error": "not found"})


@bp.route("/governance/pending")
def pending_approvals():
    return jsonify([a.to_dict() for a in _app().gov.pending()])


# ── memory ────────────────────────────────────────────────────────────────────
@bp.route("/memory")
def memory():
    app   = _app()
    query = request.args.get("q", app.ses.active_experiment or "conversion")
    similar  = app.mem.search_similar(query, limit=8)
    learnings= app.mem.get_learnings(limit=8)
    metrics  = app.mem.get_successful_metrics(limit=5)
    anomalies= app.mem.get_recent_anomalies(limit=5)
    return jsonify({
        "count":     app.mem.experiment_count(),
        "similar":   similar,
        "learnings": learnings,
        "metrics":   metrics,
        "anomalies": anomalies,
    })


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH  — structured health report via core.health
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/api/health/detail")
def health_detail():
    app = _app()
    try:
        from continum.core.health import health_report
        report = health_report(app)
    except Exception as e:
        report = {"status": "error", "error": str(e)}
    return jsonify(report), (200 if report.get("status") == "ok" else 503)


@bp.route("/api/health/dependencies")
def health_dependencies():
    try:
        from continum.core.health import check_dependencies
        deps = check_dependencies()
        return jsonify([
            {"name": d.name, "available": d.available,
             "required": d.required, "version": d.version, "ok": d.ok}
            for d in deps
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# INTELLIGENCE BUS  — expose bus snapshot for the UI panel
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/api/insights")
def insights():
    app = _app()
    try:
        bus    = app.bus
        n      = int(request.args.get("n", 20))
        recent = bus.recent(n)
        return jsonify([{
            "source":     i.source_module,
            "type":       i.insight_type.value if hasattr(i.insight_type, "value") else str(i.insight_type),
            "severity":   i.severity.value if hasattr(i.severity, "value") else str(i.severity),
            "message":    i.message,
            "detail":     i.detail,
            "created_at": i.created_at,
        } for i in recent])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/insights/next-steps")
def next_steps():
    app = _app()
    try:
        from continum.runtime.intelligence import InsightType
        bus   = app.bus
        steps = bus.by_type(InsightType.NEXT_STEP)
        return jsonify([{
            "module":  i.source_module,
            "message": i.message,
            "detail":  i.detail,
        } for i in steps[-10:]])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
