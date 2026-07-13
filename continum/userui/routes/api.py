from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from urllib.parse import quote

from flask import Blueprint, Response, current_app, jsonify, request

bp = Blueprint("api", __name__, url_prefix="/api")
logger = logging.getLogger("continum.userui.api")


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
            q.put(json.dumps({"level": "WARN", "msg": "⛔ Stopped by user", "ts": time.time()}))
            q.put(json.dumps({"level": "DONE", "msg": "__done__", "ts": time.time()}))
        return jsonify({"ok": True, "run_id": run_id})
    return jsonify({"ok": False, "error": "unknown_run_id"}), 404


# Warehouse (DuckDB gold_experiment_analysis) experiments all belong to the
# Xometry dataset (registry key "experiments").
_WAREHOUSE_DATASET = "experiments"


@bp.route("/experiments")
def experiments():
    """List experiments, optionally filtered by ``?dataset=<name>``.

    Merges two sources: the DuckDB warehouse (the shipped Xometry A/B tests,
    tagged dataset='experiments') and the user-created registry (each with its
    own dataset). A blank/absent dataset returns everything."""
    app = _app()
    dataset = (request.args.get("dataset") or "").strip()
    rows: list[dict] = []

    # Warehouse experiments — only when the (Xometry) dataset matches or no filter.
    if app.db and dataset in ("", _WAREHOUSE_DATASET):
        try:
            from continum.datastore.loader import list_experiments

            df = list_experiments(app.db)
            for rec in df.to_dict(orient="records"):
                rec["dataset"] = _WAREHOUSE_DATASET
                rec["source"] = "warehouse"
                rows.append(rec)
        except Exception as e:
            logger.warning("list_experiments failed: %s", e)

    # User-created registry experiments (persisted metadata records).
    try:
        from continum.datastore.experiment_registry import list_registry

        for r in list_registry(dataset or None):
            variants = r.get("variants") or []
            rows.append(
                {
                    "experiment_name": r.get("experiment_name"),
                    "dataset": r.get("dataset") or "",
                    "n_variants": len(variants),
                    "n_rows": 0,
                    "start_date": r.get("start_date") or "",
                    "end_date": r.get("end_date") or "",
                    "source": "registry",
                }
            )
    except Exception as e:
        logger.warning("registry list failed: %s", e)

    return jsonify(rows)


@bp.route("/experiments/create", methods=["POST"])
def create_experiment():
    """Create a new experiment metadata record under a dataset. Persists to the
    JSON registry so it survives restarts and shows up in the dropdowns."""
    from continum.askdata.metadata import list_datasets
    from continum.datastore.experiment_registry import add_experiment

    app = _app()
    body = request.get_json(silent=True) or {}
    name = (body.get("experiment_name") or body.get("name") or "").strip()
    dataset = (body.get("dataset") or "").strip()
    if not name:
        return jsonify({"error": "experiment_name is required"}), 400
    if dataset not in list_datasets():
        return jsonify({"error": f"unknown dataset: {dataset}"}), 400

    # Reject collisions with live warehouse experiment names too (not just the
    # registry, which add_experiment already guards).
    if dataset == _WAREHOUSE_DATASET and getattr(app, "db", None) is not None:
        try:
            from continum.datastore.loader import list_experiments

            existing = set(list_experiments(app.db).get("experiment_name", []))
            if name in existing:
                return jsonify({"error": f"experiment '{name}' already exists"}), 400
        except Exception:
            pass

    variants = body.get("variants")
    if isinstance(variants, str):
        variants = [v.strip() for v in variants.split(",") if v.strip()]
    try:
        record = add_experiment(
            experiment_name=name,
            dataset=dataset,
            hypothesis=body.get("hypothesis", ""),
            variants=variants,
            primary_metric=body.get("primary_metric", ""),
            start_date=body.get("start_date", ""),
            end_date=body.get("end_date", ""),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("create_experiment failed")
        return jsonify({"error": str(e)}), 500

    if getattr(app, "aud", None) is not None:
        app.aud.record("create_experiment", name, session_id=getattr(app.ses, "session_id", None))
    return jsonify({"ok": True, "experiment": record})


@bp.route("/experiments/select", methods=["POST"])
def select_experiment():
    app = _app()
    name = (request.get_json(silent=True) or {}).get("name", "")
    if name:
        app.ses.select_experiment(name)
        app.ses.save()
        app.aud.record("select_experiment", name, session_id=app.ses.session_id)
    return jsonify({"ok": True, "active": app.ses.active_experiment})


# ── modules list ──────────────────────────────────────────────────────────────
@bp.route("/modules")
def modules():
    from continum.toolinterface import _build_registry, list_modules

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
                    "ior": round(float(row[1] or 0.18), 4),
                    "monthly_inquiries": round(float(row[2] or 10000), 0),
                    "aov": round(float(row[3] or 500), 0),
                }
        except Exception:
            baselines = {
                "daily_inquiries": 500,
                "ior": 0.18,
                "monthly_inquiries": 10000,
                "aov": 500,
            }

    ior = baselines.get("ior", 0.18)
    dau = baselines.get("daily_inquiries", 500)
    mon = baselines.get("monthly_inquiries", 10000)
    aov = baselines.get("aov", 500)

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
                {
                    "key": "Baseline conversion/IOR rate (0–1)",
                    "label": "Baseline IOR rate (0–1)",
                    "type": "float",
                    "default": ior,
                    "min": 0.001,
                    "max": 0.999,
                    "help": f"Auto-detected from historical data: {ior:.4f}",
                },
                {
                    "key": "MDE — minimum detectable effect (% relative, e.g. 10)",
                    "label": "Minimum detectable effect (% relative)",
                    "type": "float",
                    "default": 10.0,
                    "min": 0.1,
                    "help": "e.g. 10 means detect a 10% relative lift",
                },
                {
                    "key": "Significance level α",
                    "label": "Significance level α",
                    "type": "float",
                    "default": 0.05,
                    "min": 0.001,
                    "max": 0.30,
                },
                {
                    "key": "Statistical power 1-β",
                    "label": "Statistical power 1−β",
                    "type": "float",
                    "default": 0.80,
                    "min": 0.50,
                    "max": 0.99,
                },
                {
                    "key": "Number of variants (including control)",
                    "label": "Number of variants (incl. control)",
                    "type": "int",
                    "default": 2,
                    "min": 2,
                },
                {
                    "key": "Daily eligible traffic",
                    "label": "Daily eligible traffic",
                    "type": "float",
                    "default": dau,
                    "min": 1,
                    "help": f"Auto-detected: {dau:,.0f} daily inquiries",
                },
                {
                    "key": "Fraction of traffic in experiment (0–1)",
                    "label": "Traffic fraction in experiment (0–1)",
                    "type": "float",
                    "default": 1.0,
                    "min": 0.01,
                    "max": 1.0,
                },
            ],
        },
        "opportunity_sizing": {
            "title": "📋 Opportunity Sizing",
            "description": "Quantify the revenue opportunity before committing to an experiment.",
            "needs_experiment": False,
            "fields": [
                {
                    "key": "monthly_inquiries",
                    "label": "Monthly inquiries",
                    "type": "float",
                    "default": mon,
                    "min": 1,
                    "help": f"Auto-detected: {mon:,.0f}/month",
                },
                {
                    "key": "current_ior_(0–1)",
                    "label": "Current IOR (0–1)",
                    "type": "float",
                    "default": ior,
                    "min": 0.001,
                    "max": 0.999,
                    "help": f"Auto-detected: {ior:.4f}",
                },
                {
                    "key": "target_ior_after_experiment_(0–1)",
                    "label": "Target IOR after experiment",
                    "type": "float",
                    "default": round(min(ior * 1.10, 0.999), 4),
                    "min": 0.001,
                    "max": 0.999,
                },
                {
                    "key": "average_order_value_($)",
                    "label": "Average order value ($)",
                    "type": "float",
                    "default": aov,
                    "min": 1,
                    "help": f"Auto-detected: ${aov:,.0f}",
                },
                {
                    "key": "gross_margin_(0–1)",
                    "label": "Gross margin (0–1)",
                    "type": "float",
                    "default": 0.30,
                    "min": 0.01,
                    "max": 1.0,
                },
                {
                    "key": "time_horizon_(months)",
                    "label": "Time horizon (months)",
                    "type": "float",
                    "default": 12.0,
                    "min": 1,
                },
            ],
        },
        "brief_generator": {
            "title": "📄 Experiment Brief Generator",
            "description": "Generate a structured experiment brief with hypothesis, metrics, and design.",
            "needs_experiment": False,
            "fields": [
                {
                    "key": "description",
                    "label": "Feature / change description",
                    "type": "text",
                    "default": "",
                    "help": "What are you testing? Be specific.",
                },
                {
                    "key": "hypothesis",
                    "label": "Hypothesis (if X then Y because Z)",
                    "type": "text",
                    "default": "",
                    "help": "e.g. If we move billing earlier, then IOR will increase by 5% because...",
                },
                {"key": "team", "label": "Team", "type": "text", "default": "Product"},
                {"key": "owner", "label": "Experiment owner", "type": "text", "default": "Analyst"},
            ],
        },
        "metrics_and_tracking": {
            "title": "📊 KPI & Tracking Plan",
            "description": "Define primary, secondary, and guardrail metrics with tracking events.",
            "needs_experiment": False,
            "fields": [
                {
                    "key": "description",
                    "label": "Feature description",
                    "type": "text",
                    "default": "",
                    "help": "Brief description of the feature being tracked",
                },
                {
                    "key": "maturity",
                    "label": "Experiment maturity",
                    "type": "select",
                    "default": "mvp",
                    "options": ["mvp", "iteration", "critical"],
                    "help": "mvp=first test, iteration=refined, critical=high-stakes",
                },
            ],
        },
        "audience_selection": {
            "title": "🎯 Advanced Audience Selection",
            "description": "Select experiment audiences using propensity modeling, causal/meta-learners, stratified sampling, or value-based targeting.",
            "needs_experiment": False,
            "fields": [
                {
                    "key": "feature_desc",
                    "label": "Feature / change description",
                    "type": "text",
                    "default": "",
                    "help": "What are you testing? e.g. 'Checkout redesign', 'New pricing page'",
                },
                {
                    "key": "category",
                    "label": "Experiment category",
                    "type": "select",
                    "default": "conversion",
                    "options": ["conversion", "acquisition", "retention", "engagement"],
                    "help": "Determines propensity weights and segment priority",
                },
                {
                    "key": "technique",
                    "label": "Selection technique",
                    "type": "select",
                    "default": "1",
                    "options": [
                        "1 — Random Sampling (uniform random draw from eligible pool)",
                        "2 — Propensity Score Matching (logistic propensity model)",
                        "3 — Stratified Sampling (proportional across segments)",
                        "4 — High-Value / Top-N Targeting (rank by CLV proxy)",
                        "5 — T-Learner (causal meta-learner for CATE estimation)",
                        "6 — S-Learner (single-model treatment effect estimation)",
                        "7 — Uplift-Based Selection (target persuadables only)",
                    ],
                    "option_values": ["1", "2", "3", "4", "5", "6", "7"],
                    "help": "Choose method. Techniques 5-7 use causal ML for optimal targeting.",
                },
                {
                    "key": "target_size",
                    "label": "Target audience size (0 = all eligible)",
                    "type": "int",
                    "default": 0,
                    "min": 0,
                    "help": "Total users across control + treatment. 0 uses all eligible users.",
                },
                {
                    "key": "control_ratio",
                    "label": "Control group ratio",
                    "type": "select",
                    "default": "0.5",
                    "options": [
                        "0.5 — Equal (50/50)",
                        "0.3 — 30% control / 70% treatment",
                        "0.2 — 20% control / 80% treatment",
                        "0.1 — 10% control / 90% treatment",
                    ],
                    "option_values": ["0.5", "0.3", "0.2", "0.1"],
                    "help": "Proportion allocated to control group",
                },
                {
                    "key": "budget_total",
                    "label": "Total budget ($, 0 = no constraint)",
                    "type": "float",
                    "default": 0.0,
                    "min": 0,
                },
                {
                    "key": "cost_per_user",
                    "label": "Cost per user ($)",
                    "type": "float",
                    "default": 0.0,
                    "min": 0,
                },
                {
                    "key": "eligibility",
                    "label": "Eligibility filter (segment keyword, blank = all)",
                    "type": "text",
                    "default": "",
                },
                {
                    "key": "exclusion",
                    "label": "Exclusion filter (segment keyword, blank = none)",
                    "type": "text",
                    "default": "",
                },
                {
                    "key": "balance_check",
                    "label": "Run covariate balance diagnostics after selection?",
                    "type": "select",
                    "default": "yes",
                    "options": ["yes", "no"],
                    "help": "Validates that control and treatment groups are balanced on key covariates",
                },
            ],
        },
        "health_monitor": {
            "title": "🩺 Experiment Health Monitor",
            "description": "SRM detection, guardrail checks, and ETA to significance.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment to monitor",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
            ],
        },
        "sequential_testing": {
            "title": "📈 Sequential Testing (mSPRT)",
            "description": "Always-valid p-values for early stopping decisions.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
                {
                    "key": "alpha",
                    "label": "Type-I error budget α",
                    "type": "float",
                    "default": 0.05,
                    "min": 0.001,
                    "max": 0.20,
                },
            ],
        },
        "experiment_analysis": {
            "title": "🔬 Full A/B Readout",
            "description": "Primary metric, segments, causal analysis, and ship recommendation.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment to analyse",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
            ],
        },
        "causal_analysis": {
            "title": "🔗 Causal Analysis",
            "description": "Choose the right causal method for your experiment design.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
                {
                    "key": "method_choice",
                    "label": "Causal method",
                    "type": "select",
                    "default": "1",
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
                    "option_values": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
                },
            ],
        },
        "simpsons_paradox": {
            "title": "🔀 Simpson's Paradox Detector",
            "description": "Check whether segment-level effects contradict the overall direction.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
            ],
        },
        "roi_tracker": {
            "title": "💰 ROI Tracker",
            "description": "Track incremental revenue post-ship.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
            ],
        },
        "learnings_repository": {
            "title": "🧠 Learnings Repository",
            "description": "Store and retrieve experiment learnings for organizational memory.",
            "needs_experiment": False,
            "fields": [
                {
                    "key": "action",
                    "label": "Action",
                    "type": "select",
                    "default": "1",
                    "options": ["1 — View / search existing learnings", "2 — Store a new learning"],
                    "option_values": ["1", "2"],
                },
                {
                    "key": "query",
                    "label": "Search query (for viewing)",
                    "type": "text",
                    "default": "conversion",
                    "help": "Keywords to search existing learnings",
                },
                {
                    "key": "experiment_name",
                    "label": "Experiment name (for storing)",
                    "type": "text",
                    "default": "",
                },
                {
                    "key": "ship_decision",
                    "label": "Ship decision",
                    "type": "select",
                    "default": "ship",
                    "options": ["ship", "no_ship", "partial_ship"],
                    "option_values": ["ship", "no_ship", "partial_ship"],
                },
                {"key": "key_learning", "label": "Key learning", "type": "text", "default": ""},
                {"key": "outcome", "label": "Outcome summary", "type": "text", "default": ""},
            ],
        },
        "uplift_modeller": {
            "title": "🚀 Uplift Modeller",
            "description": "Estimate individual-level causal effects for targeting.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
            ],
        },
        "decision_engine": {
            "title": "🎯 Decision Engine",
            "description": "Optimise targeting using uplift scores.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
            ],
        },
        # ── V4 new modules ────────────────────────────────────────────────────
        "funnel_analysis": {
            "title": "🔄 Funnel Analysis",
            "description": "Analyse conversion funnel stages, drop-off rates, and segment breakdown. Tier 1 — deterministic.",
            "needs_experiment": False,
            "fields": [],
        },
        "cohort_analysis": {
            "title": "👥 Cohort Analysis",
            "description": "Monthly cohort analysis with trend detection and retention curves. Tier 1.",
            "needs_experiment": False,
            "fields": [],
        },
        "retention_analysis": {
            "title": "📉 Retention Analysis",
            "description": "Repeat purchase and retention rate analysis by segment. Tier 1.",
            "needs_experiment": False,
            "fields": [],
        },
        "churn_analysis": {
            "title": "🔎 Churn Analysis",
            "description": "Activity-based churn detection with 30/60/90 day windows. Tier 1.",
            "needs_experiment": False,
            "fields": [],
        },
        "journey_analysis": {
            "title": "🗺️ Journey Analysis",
            "description": "User journey pattern analysis: touchpoints, journey length, path-to-conversion. Tier 1.",
            "needs_experiment": False,
            "fields": [],
        },
        "opportunity_ranking": {
            "title": "⭐ Opportunity Ranking",
            "description": "Score and rank opportunities by impact, confidence, and reach. Tier 1.",
            "needs_experiment": False,
            "fields": [],
        },
        "hypothesis_generation": {
            "title": "💡 Hypothesis Generation",
            "description": "Generate experiment hypotheses with structured assumptions, counter-hypotheses, and risks. Tier 3 — LLM.",
            "needs_experiment": False,
            "fields": [
                {
                    "key": "description",
                    "label": "Feature / opportunity description",
                    "type": "textarea",
                    "default": "",
                    "help": "Describe what you want to test. LLM will generate structured hypotheses.",
                },
            ],
        },
        "experiment_design": {
            "title": "🧪 Experiment Design Recommender",
            "description": "Recommend the best experiment methodology (A/B, DiD, ITS, PSM, Geo, etc.) based on constraints. Tier 1.",
            "needs_experiment": False,
            "fields": [
                {
                    "key": "description",
                    "label": "What are you testing?",
                    "type": "text",
                    "default": "",
                },
                {
                    "key": "randomization_unit",
                    "label": "Randomization unit",
                    "type": "select",
                    "default": "user",
                    "options": ["user", "session", "geo", "store", "cluster"],
                    "help": "At what level can you randomize?",
                },
                {
                    "key": "full_rollout",
                    "label": "Is this a 100% rollout (no control)?",
                    "type": "select",
                    "default": "no",
                    "options": ["no", "yes"],
                },
                {
                    "key": "has_pre_data",
                    "label": "Do you have pre-period historical data?",
                    "type": "select",
                    "default": "yes",
                    "options": ["yes", "no"],
                },
            ],
        },
        "bayesian_analysis": {
            "title": "🎲 Bayesian A/B Analysis",
            "description": "Bayesian A/B test with Beta posteriors, credible intervals, and P(B>A). Tier 1.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
            ],
        },
        "segment_deep_dive": {
            "title": "🔬 Segment Deep Dive",
            "description": "Segment-level treatment effects with best/worst segment identification. Tier 1.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
            ],
        },
        "driver_discovery": {
            "title": "🔑 Driver Discovery",
            "description": "Identify the key drivers of conversion using group-level impact scoring. Tier 1.",
            "needs_experiment": False,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment (optional — blank for overall)",
                    "type": "text",
                    "default": "",
                },
            ],
        },
        "readout_generator": {
            "title": "📝 Readout Generator",
            "description": "Generate a full experiment readout document. Tier 2 — LLM optional.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
            ],
        },
        "executive_summary": {
            "title": "📋 Executive Summary",
            "description": "Generate a one-page executive summary. Tier 2 — LLM optional.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
            ],
        },
        "long_term_effects": {
            "title": "📉 Long-Term Effects Analysis",
            "description": "Persistence and decay analysis of treatment effects over time. Tier 1.",
            "needs_experiment": True,
            "fields": [
                {
                    "key": "experiment_name",
                    "label": "Experiment",
                    "type": "experiment_select",
                    "default": "",
                    "options": experiments,
                },
            ],
        },
        "portfolio_management": {
            "title": "📊 Experiment Portfolio",
            "description": "Portfolio overview: experiment success rates, ROI leaderboard, and team impact tracking. Tier 1.",
            "needs_experiment": False,
            "fields": [],
        },
    }

    cfg = CONFIGS.get(module_key)
    if cfg is None:
        # A10 — every module shows a real description when clicked. Modules without
        # a hardcoded form fall back to the live registry's description (and whether
        # they need an experiment) instead of a generic "Run this module.".
        desc, needs_exp = "", False
        try:
            from continum.toolinterface import get_module

            spec = get_module(module_key)
            if spec is not None:
                desc = (getattr(spec, "description", "") or "").strip()
                needs_exp = module_key in _EXPERIMENT_SCOPED_TARGETS
        except Exception:
            pass
        cfg = {
            "title": module_key.replace("_", " ").title(),
            "description": desc or "Run this module against the connected dataset.",
            "needs_experiment": needs_exp,
            "fields": [],
        }
    cfg["experiments"] = experiments
    return cfg


# ── execute + SSE stream ──────────────────────────────────────────────────────
@bp.route("/execute/<module_key>", methods=["POST"])
def execute(module_key: str):
    app = _app()
    run_id = str(uuid.uuid4())[:8]
    q: queue.Queue = queue.Queue()
    app.stream_queues[run_id] = q
    body = request.get_json(silent=True) or {}
    form_fields = body.get("fields", {})  # user-supplied field values from the config form
    exp = (
        form_fields.get("experiment_name")
        or body.get("experiment_name")
        or app.ses.active_experiment
    )

    def _worker():
        import builtins
        import io
        import sys

        from continum.toolinterface import _build_registry, get_module, run_module

        _build_registry()

        def is_stopped():
            se = getattr(app, "stop_events", {}).get(run_id)
            return se is not None and se.is_set()

        def emit(level, msg):
            if msg and str(msg).strip():
                q.put(
                    json.dumps(
                        {"level": level, "msg": str(msg).rstrip(), "ts": round(time.time(), 3)}
                    )
                )

        # ── Stdout capture → SSE queue ────────────────────────────────────────
        # Every print() in every module will appear in the UI console in real time
        _orig_stdout = sys.stdout
        _buf = []

        class _QueueWriter(io.TextIOBase):
            encoding = getattr(_orig_stdout, "encoding", "utf-8") or "utf-8"
            errors = "replace"

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

            def writable(self):
                return True

            def readable(self):
                return False

            def seekable(self):
                return False

            def isatty(self):
                return False

            def closed(self):
                return False

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
            emit("ERR", f"Module '{module_key}' not found in registry.")
            emit("DONE", "__done__")
            return

        # Build kwargs: module defaults first, user form input on top (higher priority)
        kw = {}
        kw.update(_build_default_kwargs(module_key, exp, app))
        kw.update(form_fields)  # user's actual input always wins
        # Only inject experiment_name for modules that operate on experiments
        _EXP_MODULES = {
            "health_monitor",
            "sequential_testing",
            "experiment_analysis",
            "causal_analysis",
            "causal_analysis_full",
            "simpsons_paradox",
            "roi_tracker",
            "pre_post_analysis",
            "uplift_modeller",
            "decision_engine",
            "learnings_repository",
            "brief_generator",
            # V4 experiment-scoped modules
            "bayesian_analysis",
            "segment_deep_dive",
            "readout_generator",
            "executive_summary",
            "long_term_effects",
        }
        if exp and module_key in _EXP_MODULES:
            kw["experiment_name"] = kw.get("experiment_name") or exp
            kw["experiment_id"] = kw.get("experiment_id") or exp
        if "method_choice" in kw:
            kw["method_choice"] = str(kw["method_choice"]).split(" ")[0].strip()

        # Build answer_map for input() safety net
        answer_map = _build_answer_map(module_key, kw)

        # Patch input() — thread-local, always restored in finally
        _orig_input = builtins.input
        # There is no interactive stdin in a web run. We auto-answer from the
        # form (answer_map) and otherwise return "" so prompts that treat blank
        # as "use the default" work. But a module that re-prompts on the blank
        # would spin forever, so we break any such loop and fail cleanly.
        _in_state = {"total": 0, "last": None, "repeat": 0}

        def _smart_input(prompt=""):
            p = str(prompt).lower()
            for fragment, answer in answer_map.items():
                if fragment and fragment in p:
                    emit("INFO", f"Input: {str(prompt).split('[')[0].strip()} -> {answer}")
                    return str(answer)
            # Unmapped prompt — no way for the user to answer in a web run.
            _in_state["total"] += 1
            if p == _in_state["last"]:
                _in_state["repeat"] += 1
            else:
                _in_state["last"], _in_state["repeat"] = p, 0
            if _in_state["repeat"] >= 3 or _in_state["total"] > 100:
                raise EOFError(
                    "This module is waiting for input that can't be provided from the "
                    "app. Run it from a card and fill in the fields, or supply the "
                    "missing parameter."
                )
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
                        "baseline_ior",
                        "ior",
                        "current_ior",
                        "aov",
                        "daily_inquiries",
                        "monthly_inquiries",
                        "daily_eligible_traffic",
                        # session/identity
                        "experiment_name",
                        "experiment_id",
                        "session_id",
                        "client_name",
                        # power_calculator defaults
                        "Baseline conversion/IOR rate (0-1)",
                        "MDE — minimum detectable effect (% relative, e.g. 10)",
                        "Significance level α",
                        "Statistical power 1-β",
                        "Number of variants (including control)",
                        "Daily eligible traffic",
                        "Fraction of traffic in experiment (0-1)",
                        # opportunity_sizing defaults
                        "target_ior",
                        "avg_aov",
                        "gross_margin",
                        "horizon",
                        "monthly_inquiries",
                        # other module defaults
                        "category",
                        "experiment_type",
                        "maturity",
                        "action",
                        "query",
                        # generic scheduling/prompt params
                        "select experiment",
                        "method_choice",
                    }
                    _safe_kw = {k: v for k, v in kw.items() if k not in _AUTO_INJECTED}
                    result = run_module(
                        module_key, state=app.state, llm=app.llm, db=app.db, **_safe_kw
                    )
                else:
                    raise
            elapsed = time.monotonic() - t0

            from continum.orchestrator import _summarise

            summary = _summarise(result, module_key)
            app.ses.set(f"{module_key}_result", result)
            app.ses.set("experiment_result", result)
            app.ses.record_run(module_key, spec.phase, elapsed, ok=True, summary=summary)
            app.ses.save()

            from continum.insights.insight_bus import publish_next_steps

            publish_next_steps(module_key, app.bus)
            app.bus.success(module_key, f"{module_key} completed in {elapsed:.2f}s  {summary}")
            app.aud.record(
                "module_run",
                module_key,
                {"elapsed_s": round(elapsed, 2), "summary": summary, "ok": True},
                session_id=app.ses.session_id,
            )
            try:
                from continum.askdata.narrative_runtime import get_narrative

                nr = get_narrative(bus=app.bus, session=app.ses, memory=app.mem)
                nr.after_module(module_key, result)
            except Exception:
                pass

            # ── Collect every run's output into structured nested folders ────────
            # Files the module generated are copied into OUTPUTS_DIR/<company>/<experiment>/;
            # a text-only result is written there as a .md so EVERY run leaves a browsable,
            # downloadable artifact in the Output tab.
            import os
            import re
            import shutil
            from datetime import datetime

            from continum.askdata import readout as _readout
            from continum.crosscutting.runtime_config import ensure_outputs_dir

            def _sanitize_path_segment(s: str) -> str:
                if not s:
                    return "general"
                s = re.sub(r"[^a-zA-Z0-9_\-]", "_", s)
                s = s.strip("_")
                return s or "general"

            company = _sanitize_path_segment(
                app.ses.active_dataset or app.ses.client_name or "general"
            )
            experiment = _sanitize_path_segment(exp or "general")
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

            outputs_dir = ensure_outputs_dir()
            dest_dir = os.path.join(outputs_dir, company, experiment)
            os.makedirs(dest_dir, exist_ok=True)
            collected: list[str] = []

            # Gather all potential output files from the result dictionary
            raw_outputs = []
            if isinstance(result, dict):
                _outs = result.get("_outputs")
                if _outs:
                    if isinstance(_outs, list):
                        raw_outputs.extend(_outs)
                    elif isinstance(_outs, str):
                        raw_outputs.append(_outs)

                # Include other robust keys returned by modules (e.g. output_file, result_file, csv_path)
                for k in ["output_file", "result_file", "csv_path"]:
                    val = result.get(k)
                    if val and isinstance(val, str) and val not in raw_outputs:
                        raw_outputs.append(val)

            # Only copy files that actually exist
            raw_outputs = [fp for fp in raw_outputs if os.path.exists(fp)]

            if raw_outputs:
                for fpath in raw_outputs:
                    orig_name = os.path.basename(fpath)
                    orig_base, ext = os.path.splitext(orig_name)
                    new_name = f"{orig_base}_{company}_{experiment}_{timestamp}{ext}"
                    dest = os.path.join(dest_dir, new_name)
                    try:
                        if os.path.abspath(fpath) != os.path.abspath(dest):
                            shutil.copy2(fpath, dest)
                        collected.append(dest)
                    except Exception:
                        logger.warning(
                            "could not copy output %s into outputs folder", fpath, exc_info=True
                        )
                        collected.append(fpath)  # fall back to the original path
            else:
                # No file artifact — persist the result text as markdown so it's
                # still accessible from the outputs folder.
                try:
                    _rtext = _readout.result_to_text(result, summary, module_key)
                    new_name = f"{module_key}_{company}_{experiment}_{timestamp}.md"
                    dest = os.path.join(dest_dir, new_name)
                    with open(dest, "w", encoding="utf-8") as _fh:
                        _fh.write(_rtext or f"# {module_key}\n\n{summary or '(no textual result)'}")
                    collected.append(dest)
                except Exception:
                    logger.warning("could not write result text to outputs folder", exc_info=True)

            if collected:
                emit("SEP", "─" * 60)
                emit("FILES", f"📁 {len(collected)} file(s) saved to the outputs folder:")
                for fpath in collected:
                    emit("FILE", f"  {os.path.basename(fpath)}||{fpath}")
            emit("SEP", "─" * 60)
            # Persist file list for /api/outputs/<run_id>
            app.stream_queues[f"files_{run_id}"] = collected
            # Register text-bearing files (PDF/TXT/MD) so the chat can still answer
            # questions grounded in what this run produced.
            try:
                _nr = sum(
                    1
                    for _fp in collected
                    if _readout.add_generated(app, _fp, module=module_key, run_id=run_id)
                )
                if _nr:
                    emit(
                        "INFO",
                        f"📄 Saved to the outputs folder — ask me about {'them' if _nr > 1 else 'it'}.",
                    )
            except Exception:
                logger.warning("output auto-register failed", exc_info=True)
            emit("OK", f"✅ {module_key} completed in {elapsed:.2f}s")
            if summary:
                emit("SUMMARY", summary)
            emit("DONE", "__done__")

        except Exception as e:
            import traceback

            elapsed = time.monotonic() - t0
            tb_lines = traceback.format_exc().strip().split("\n")
            emit("SEP", "─" * 60)
            emit("ERR", f"❌ {type(e).__name__}: {str(e)[:250]}")
            # Show relevant traceback lines
            for tb_line in tb_lines[-6:]:
                stripped = tb_line.strip()
                if stripped and not stripped.startswith("Traceback"):
                    emit("ERR", f"  {stripped[:180]}")
            emit("SEP", "─" * 60)
            emit("ERR", f"Module failed after {elapsed:.2f}s")
            emit("DONE", "__done__")
            app.ses.record_run(
                module_key, getattr(spec, "phase", "?"), elapsed, ok=False, error=str(e)
            )
            app.ses.save()
            app.aud.record(
                "module_run",
                module_key,
                {"error": str(e), "ok": False},
                ok=False,
                session_id=app.ses.session_id,
            )
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


def _serve_file_allowed_dirs() -> list:
    """Absolute dirs whose files /api/file may serve."""
    import os

    from continum.crosscutting.runtime_config import OUTPUTS_DIR

    home_out = os.path.join(os.path.expanduser("~"), "continum_outputs")
    cands = [
        OUTPUTS_DIR,
        "/tmp/continum_outputs",
        home_out,
        os.environ.get("CONTINUM_OUTPUT_DIR", ""),
    ]
    return [os.path.abspath(a) for a in cands if a]


@bp.route("/outputs/<run_id>")
def list_run_outputs(run_id: str):
    import os

    app = _app()
    files = app.stream_queues.get(f"files_{run_id}", [])
    out = []
    for fpath in files:
        if os.path.exists(fpath):
            out.append(
                {
                    "name": os.path.basename(fpath),
                    "path": fpath,
                    "url": "/api/file?path=" + quote(fpath),
                    "size": os.path.getsize(fpath),
                }
            )
    return jsonify(out)


@bp.route("/outputs")
def list_all_outputs():
    """Everything in the outputs folder — the browsable Output tab (B4)."""
    import os

    from continum.crosscutting.runtime_config import OUTPUTS_DIR, ensure_outputs_dir

    ensure_outputs_dir()
    out = []
    try:
        for root, dirs, files in os.walk(OUTPUTS_DIR):
            for file in files:
                fpath = os.path.join(root, file)
                if not os.path.isfile(fpath):
                    continue
                st = os.stat(fpath)
                rel_path = os.path.relpath(fpath, OUTPUTS_DIR)
                display_name = rel_path.replace(os.sep, " / ")
                out.append(
                    {
                        "name": display_name,
                        "path": fpath,
                        "url": "/api/file?path=" + quote(fpath),
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "ext": os.path.splitext(file)[1].lower().lstrip("."),
                    }
                )
    except Exception:
        logger.exception("list outputs failed")
    out.sort(key=lambda r: r.get("mtime", 0), reverse=True)
    return jsonify({"dir": os.path.abspath(OUTPUTS_DIR), "files": out})


@bp.route("/file")
def serve_file():
    import os

    from flask import abort
    from flask import send_file as _sf

    fpath = request.args.get("path", "")
    if not fpath:
        return abort(404)
    fpath = os.path.abspath(fpath)
    if not os.path.exists(fpath) or not os.path.isfile(fpath):
        return abort(404)
    # Security: only serve files that live inside an allowed output directory.
    ok = False
    for adir in _serve_file_allowed_dirs():
        try:
            if os.path.commonpath([fpath, adir]) == adir:
                ok = True
                break
        except ValueError:  # different drive on Windows
            continue
    if not ok:
        return abort(403)
    return _sf(fpath, as_attachment=False)


def _build_default_kwargs(module_key: str, exp: str, app) -> dict:
    kw: dict = {}
    # Experiment / session defaults
    if exp:
        kw["experiment_name"] = exp
        kw["experiment_id"] = exp

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
                kw.update(
                    {
                        "baseline_ior": float(row[0] or 0.18),
                        "ior": float(row[0] or 0.18),
                        "current_ior": float(row[0] or 0.18),
                        "aov": float(row[1] or 4000),
                        "daily_inquiries": float(row[2] or 500),
                        "monthly_inquiries": float(row[2] or 500) * 30.4,
                        "daily_eligible_traffic": float(row[2] or 500),
                    }
                )
        except Exception:
            kw.setdefault("baseline_ior", 0.18)
            kw.setdefault("ior", 0.18)
            kw.setdefault("aov", 4000.0)
            kw.setdefault("daily_inquiries", 500.0)

    # Session-level defaults
    ses = getattr(app, "ses", None)
    if ses is not None:
        kw.setdefault("session_id", getattr(ses, "session_id", "default"))
        kw.setdefault("client_name", getattr(ses, "client_name", "demo"))

    # Module-specific defaults
    defaults_map = {
        "power_calculator": {
            "Baseline conversion/IOR rate (0-1)": kw.get("baseline_ior", 0.18),
            "MDE — minimum detectable effect (% relative, e.g. 10)": 10.0,
            "Significance level α": 0.05,
            "Statistical power 1-β": 0.80,
            "Number of variants (including control)": 2,
            "Daily eligible traffic": kw.get("daily_inquiries", 500),
            "Fraction of traffic in experiment (0-1)": 1.0,
        },
        "opportunity_sizing": {
            "monthly_inquiries": kw.get("monthly_inquiries", 15000),
            "current_ior": kw.get("ior", 0.18),
            "target_ior": min(kw.get("ior", 0.18) * 1.10, 0.999),
            "avg_aov": kw.get("aov", 4000),
            "gross_margin": 0.30,
            "horizon": 12,
        },
        "health_monitor": {"select experiment": "1"},
        "sequential_testing": {"select experiment": "1"},
        "causal_analysis": {"method_choice": "1"},
        "audience_selection": {
            "category": "conversion",
            "feature_desc": "",
            "technique": "1",
            "target_size": 0,
            "budget_total": 0.0,
            "cost_per_user": 0.0,
            "eligibility": "",
            "exclusion": "",
            "control_ratio": "0.5",
        },
        "brief_generator": {
            "description": "Checkout funnel optimisation",
            "method": "ab_test",
            "hypothesis": "Reducing friction will increase IOR",
            "target_audience": "Active buyers",
        },
        "metrics_and_tracking": {
            "experiment_type": "conversion",
            "maturity": "mvp",
        },
        "learnings_repository": {
            "action": "1",
            "query": exp or "conversion",
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
        if "baseline conversion/ior rate (0" in "".join(m):
            pass  # already mapped by key
        # Add common variants
        m.update(
            {
                "baseline conversion": str(
                    kw.get("Baseline conversion/IOR rate (0–1)", kw.get("baseline_ior", 0.18))
                ),
                "minimum detectable effect": str(
                    kw.get(
                        "MDE — minimum detectable effect (% relative, e.g. 10)",
                        kw.get("mde_pct", 10.0),
                    )
                ),
                "significance level": str(kw.get("Significance level α", kw.get("alpha", 0.05))),
                "statistical power": str(
                    kw.get("Statistical power 1-β", kw.get("power_val", 0.80))
                ),
                "number of variants": str(
                    kw.get("Number of variants (including control)", kw.get("n_variants", 2))
                ),
                "daily eligible traffic": str(
                    kw.get("Daily eligible traffic", kw.get("daily_users", 500))
                ),
                "fraction of traffic": str(
                    kw.get("Fraction of traffic in experiment (0–1)", kw.get("traffic_share", 1.0))
                ),
            }
        )
    elif module_key == "opportunity_sizing":
        m.update(
            {
                "monthly inquiries": str(kw.get("monthly_inquiries", 10000)),
                "current ior": str(kw.get("current_ior_(0–1)", 0.18)),
                "target ior": str(kw.get("target_ior_after_experiment_(0–1)", 0.198)),
                "average order value": str(kw.get("average_order_value_($)", 500)),
                "gross margin": str(kw.get("gross_margin_(0–1)", 0.30)),
                "time horizon": str(kw.get("time_horizon_(months)", 12)),
            }
        )
    elif module_key == "audience_selection":
        cat_map = {"conversion": "1", "acquisition": "2", "retention": "3", "engagement": "4"}
        cat = kw.get("category", "conversion")
        m["experiment category"] = cat_map.get(cat, "1")
        m["category"] = str(cat)
        m["feature_desc"] = str(kw.get("feature_desc", ""))
        m["technique"] = str(kw.get("technique", "1")).split()[0]
        m["target_size"] = str(kw.get("target_size", "0"))
        m["budget_total"] = str(kw.get("budget_total", "0"))
        m["cost_per_user"] = str(kw.get("cost_per_user", "0"))
        m["eligibility"] = str(kw.get("eligibility", ""))
        m["exclusion"] = str(kw.get("exclusion", ""))
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
        m["choose [1/2/3]"] = str(kw.get("action", "1"))
        m["search query"] = str(kw.get("query", "conversion"))
        m["experiment name"] = str(kw.get("experiment_name", ""))
        m["ship decision"] = str(kw.get("ship_decision", "ship"))
        m["key learning"] = str(kw.get("key_learning", "Stored from UI"))
        m["outcome summary"] = str(kw.get("outcome", "Completed via UI"))
        m["what worked"] = str(kw.get("what_worked", "Treatment variant"))
        m["what did not"] = "N/A"
        m["recommendation"] = str(kw.get("recommendation", "Review analysis"))
        m["follow-up ideas"] = ""
        m["tags"] = "ui"
    elif module_key == "schema_discovery":
        m["client / project name"] = str(kw.get("client_name", "demo"))
        m["client_name"] = str(kw.get("client_name", "demo"))
    return m


@bp.route("/stream/<run_id>")
def stream(run_id: str):
    app = _app()
    q = app.stream_queues.get(run_id)
    if q is None:
        return Response(
            'data: {"level":"ERR","msg":"unknown run_id"}\n\n', mimetype="text/event-stream"
        )

    def _gen():
        while True:
            try:
                msg = q.get(timeout=30)
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
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8",
        },
        direct_passthrough=True,
    )


# ── session ───────────────────────────────────────────────────────────────────
@bp.route("/session")
def session_state():
    app = _app()
    s = app.ses
    return jsonify(
        {
            "session_id": s.session_id,
            "client_name": s.client_name,
            "active_experiment": s.active_experiment,
            "active_metrics": s.active_metrics,
            "n_runs": len(s.execution_history),
            "history": [
                {
                    "module": r.module,
                    "ok": r.ok,
                    "elapsed": round(r.elapsed_s, 2),
                    "summary": r.summary,
                    "phase": r.phase,
                }
                for r in s.execution_history[-20:]
            ],
            "recommendations": [
                {"action": r.action, "reason": r.reason, "priority": r.priority}
                for r in s.recommendations[:5]
            ],
            "context_keys": list(s._context.keys()),
        }
    )


@bp.route("/session/fork", methods=["POST"])
def fork_session():
    app = _app()
    label = (request.get_json(silent=True) or {}).get("label", "")
    fork = app.ses.fork(label=label or None)
    # Switch the app to the fork
    app.ses = fork
    fork.db = app.db
    fork.state = app.state
    app.aud.record("session_fork", fork.session_id, {"parent": fork._parent_id, "label": label})
    return jsonify(
        {
            "ok": True,
            "session_id": fork.session_id,
            "description": getattr(fork, "fork_description", ""),
        }
    )


@bp.route("/session/snapshot", methods=["POST"])
def snapshot():
    app = _app()
    label = (request.get_json(silent=True) or {}).get("label", "")
    sid = app.snap.take(app.ses, bus=app.bus, label=label)
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
        return {
            "type": i.insight_type,
            "severity": i.severity,
            "source": i.source_module,
            "message": i.message,
            "detail": i.detail,
        }

    return jsonify(
        {
            "insights": [_d(i) for i in bus.all()[-30:]],
            "warnings": [_d(i) for i in bus.warnings()],
            "recommendations": [_d(i) for i in bus.recommendations()],
            "kpis": [_d(i) for i in bus.kpi_suggestions()],
        }
    )


# ── inspect ───────────────────────────────────────────────────────────────────
@bp.route("/inspect/<what>")
def inspect_endpoint(what: str):
    app = _app()
    from continum.datastore.inspect import inspect

    report = inspect(what, session=app.ses, db=app.db, bus=app.bus, memory=app.mem)
    return jsonify(report)


@bp.route("/inspect")
def inspect_all():
    app = _app()
    from continum.datastore.inspect import inspect_all

    return jsonify(inspect_all(session=app.ses, db=app.db, bus=app.bus, memory=app.mem))


# ── compare ───────────────────────────────────────────────────────────────────
@bp.route("/compare", methods=["POST"])
def compare():
    app = _app()
    body = request.get_json(silent=True) or {}
    a = body.get("experiment_a", "").strip()
    b = body.get("experiment_b", "").strip()
    if not a or not b:
        return jsonify({"error": "Provide experiment_a and experiment_b"}), 400
    if not app.db:
        return jsonify({"error": "No database connected"}), 503

    from continum.experimentation.compare import _extract_metrics, _synthesise
    from continum.toolinterface import _build_registry, run_module

    _build_registry()
    results = {}
    for name in [a, b]:
        try:
            r = run_module(
                "experiment_analysis",
                state=app.state,
                llm=app.llm,
                db=app.db,
                experiment_name=name,
                experiment_id=name,
            )
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

    return jsonify(
        {
            "experiment_a": {"name": a, "metrics": _s(ma)},
            "experiment_b": {"name": b, "metrics": _s(mb)},
            "narrative": _synthesise(a, ma, b, mb),
        }
    )


# ── lineage ───────────────────────────────────────────────────────────────────
@bp.route("/lineage")
def lineage():
    app = _app()
    from continum.datastore.inspect import inspect

    return jsonify(inspect("lineage", session=app.ses, db=app.db))


# ── audit ─────────────────────────────────────────────────────────────────────
@bp.route("/llm/status")
def llm_status_endpoint():
    from continum.crosscutting.llm import llm_status

    return jsonify(llm_status())


@bp.route("/llm/load", methods=["POST"])
def llm_load():
    import threading

    app = _app()

    def _load():
        try:
            from continum.crosscutting.llm import load_llm

            app.llm = load_llm()
            st = app.llm.status()
            app.bus.success("llm", f"LLM loaded on {st.get('device', 'unknown')}")
            app.aud.record(
                "llm_load",
                st.get("model_id", "LLM"),
                {"device": st.get("device", "unknown")},
                session_id=app.ses.session_id,
            )
        except Exception as e:
            app.bus.warn("llm", f"LLM load failed: {str(e)[:120]}")
            logger.exception("LLM load failed")

    threading.Thread(target=_load, daemon=True).start()
    return jsonify({"ok": True, "message": "Model loading in background — check /api/llm/status"})


@bp.route("/llm/unload", methods=["POST"])
def llm_unload():
    app = _app()
    from continum.crosscutting.llm import unload_llm

    unload_llm()
    app.llm = None
    return jsonify({"ok": True, "message": "Model unloaded"})


@bp.route("/narrative")
def narrative():
    app = _app()
    from continum.askdata.narrative_runtime import get_narrative

    nr = get_narrative(bus=app.bus, session=app.ses, memory=app.mem)

    stream = nr.get_stream(n=15)
    # If stream is thin, inject a fresh thought
    if len(stream) < 3:
        thought = nr.idle_thought()
        if thought:
            stream.insert(
                0,
                {
                    "text": thought,
                    "source": "observation",
                    "created_at": __import__("datetime").datetime.utcnow().isoformat()[:19],
                },
            )
    return jsonify(stream)


@bp.route("/patterns")
def patterns():
    app = _app()
    from continum.insights.patterns import get_miner

    miner = get_miner(app.mem)
    report = miner.mine_all()
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
    app = _app()
    body = request.get_json(silent=True) or {}
    exp = body.get("experiment_id") or app.ses.active_experiment
    if not exp:
        return jsonify({"error": "No experiment_id"}), 400
    approval = app.gov.request_ship(exp, requested_by=body.get("analyst", "analyst"))
    return jsonify(approval.to_dict())


@bp.route("/governance/approve", methods=["POST"])
def approve_ship():
    app = _app()
    body = request.get_json(silent=True) or {}
    exp = body.get("experiment_id", "")
    a = app.gov.approve_ship(
        exp, reviewed_by=body.get("reviewer", "reviewer"), comment=body.get("comment", "")
    )
    return jsonify(a.to_dict() if a else {"error": "not found"})


@bp.route("/governance/pending")
def pending_approvals():
    return jsonify([a.to_dict() for a in _app().gov.pending()])


# ── memory ────────────────────────────────────────────────────────────────────
@bp.route("/memory")
def memory():
    app = _app()
    query = request.args.get("q", app.ses.active_experiment or "conversion")
    similar = app.mem.search_similar(query, limit=8)
    learnings = app.mem.get_learnings(limit=8)
    metrics = app.mem.get_successful_metrics(limit=5)
    anomalies = app.mem.get_recent_anomalies(limit=5)
    return jsonify(
        {
            "count": app.mem.experiment_count(),
            "similar": similar,
            "learnings": learnings,
            "metrics": metrics,
            "anomalies": anomalies,
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH  — structured health report via core.health
# ─────────────────────────────────────────────────────────────────────────────


@bp.route("/health/detail")
def health_detail():
    app = _app()
    try:
        from continum.userui.health import health_report

        report = health_report(app)
    except Exception as e:
        report = {"status": "error", "error": str(e)}
    return jsonify(report), (200 if report.get("status") == "ok" else 503)


@bp.route("/health/dependencies")
def health_dependencies():
    try:
        from continum.userui.health import check_dependencies

        deps = check_dependencies()
        return jsonify(
            [
                {
                    "name": d.name,
                    "available": d.available,
                    "required": d.required,
                    "version": d.version,
                    "ok": d.ok,
                }
                for d in deps
            ]
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# INTELLIGENCE BUS  — expose bus snapshot for the UI panel
# ─────────────────────────────────────────────────────────────────────────────


@bp.route("/insights")
def insights():
    app = _app()
    try:
        bus = app.bus
        n = int(request.args.get("n", 20))
        recent = bus.recent(n)
        return jsonify(
            [
                {
                    "source": i.source_module,
                    "type": (
                        i.insight_type.value
                        if hasattr(i.insight_type, "value")
                        else str(i.insight_type)
                    ),
                    "severity": (
                        i.severity.value if hasattr(i.severity, "value") else str(i.severity)
                    ),
                    "message": i.message,
                    "detail": i.detail,
                    "created_at": i.created_at,
                }
                for i in recent
            ]
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/insights/next-steps")
def next_steps():
    app = _app()
    try:
        from continum.insights.insight_bus import InsightType

        bus = app.bus
        steps = bus.by_type(InsightType.NEXT_STEP)
        return jsonify(
            [
                {
                    "module": i.source_module,
                    "message": i.message,
                    "detail": i.detail,
                }
                for i in steps[-10:]
            ]
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# COPILOT  — powers the collapsible right-hand assistant pane.
#   • guide   : RAG over the README(s) (how-to / "about the tool" questions)
#   • data    : AskData multi-agent LangGraph engine (NL→SQL→insight over its
#               dataset); also answers "about itself" questions from the README
#   • auto    : routes guide-vs-data from the question text; the data path is
#               the AskData engine (replaces the legacy ContinumCopilot)
# Provide Azure/OpenAI creds (.env or .streamlit/secrets.toml) to run the engine
# on GPT-4o; otherwise it uses a local fallback model. See runtime/ask/askdata/.
# ─────────────────────────────────────────────────────────────────────────────

# Tools whose underlying module is scoped to a single experiment — running them
# without an active/selected experiment yields a misleading "no data" answer, so
# the copilot calls them out instead (A7).
_EXPERIMENT_SCOPED_TARGETS = {
    "experiment_analysis",
    "causal_analysis",
    "causal_analysis_full",
    "health_monitor",
    "uplift_modeller",
    "decision_engine",
    "sequential_testing",
    "bayesian_analysis",
    "segment_deep_dive",
}


def _active_experiment(app, ui_context: dict) -> str:
    return (
        str((ui_context or {}).get("active_experiment") or "").strip()
        or str(getattr(getattr(app, "ses", None), "active_experiment", "") or "").strip()
    )


def _needs_experiment_callout(tool, app, ui_context: dict):
    """Return a friendly callout string if `tool` needs an experiment and none is
    active, else None."""
    if tool is None or getattr(tool, "target", None) not in _EXPERIMENT_SCOPED_TARGETS:
        return None
    if _active_experiment(app, ui_context):
        return None
    return (
        f"**{tool.module_name}** runs against a single experiment, but no experiment "
        f"is selected yet. Pick one from the **experiment dropdown** in the top bar "
        f"(or tell me which experiment), then ask again."
    )


# Deictic experiment references — these questions are meaningless without an
# experiment selected ("the/this/active experiment"), so they're gated even
# though they don't name a module. Portfolio phrasing ("experiments impacting
# revenue") deliberately does NOT match, so cross-experiment questions still flow.
_EXPERIMENT_DEICTIC_KW = (
    "this experiment",
    "the experiment",
    "active experiment",
    "current experiment",
    "selected experiment",
    "my experiment",
    "this test",
    "the readout",
)


def _active_dataset(app) -> str:
    return str(getattr(getattr(app, "ses", None), "active_dataset", "") or "").strip()


def _question_is_experiment_scoped(q: str) -> bool:
    ql = (q or "").lower()
    return any(k in ql for k in _EXPERIMENT_DEICTIC_KW)


def _gate_response(q: str, gate_mode: str, response: str, llm_loaded: bool) -> dict:
    """The JSON shape the copilot front end expects for a non-answer prompt
    (mirrors the existing ``needs_experiment`` payload)."""
    return {
        "question": q,
        "response": response,
        "mode": gate_mode,
        "sql": None,
        "table": [],
        "columns": [],
        "visualizations": [],
        "pending_tool": None,
        "deploy_warning": None,
        "next_steps": [],
        "suggestions": [],
        "llm_loaded": llm_loaded,
        "error": None,
    }


def _selection_gate(app, q: str, ui_context: dict, confirm_key: str, llm_loaded: bool):
    """Enforce the dropdown selection flow in chat. Returns a gate payload dict to
    short-circuit the answer, or None to proceed.

      • capability / how-to / meta questions → always allowed (None)
      • no dataset selected → prompt to pick a dataset/company first
      • experiment-scoped question with no experiment selected → prompt to pick one
    """
    # Meta/help/how-to always answer, even before any selection.
    if _is_meta_q(q) or _auto_mode(q) == "guide":
        return None
    if not _active_dataset(app):
        return _gate_response(
            q,
            "needs_dataset",
            "Pick a **dataset / company** from the dropdown at the top of the Copilot "
            "(or the top bar) before we dig into the data — that tells me which company's "
            "experiments to reason about.",
            llm_loaded,
        )
    # A confirmed module is gated by _needs_experiment_callout (more precise);
    # here we only catch free-text experiment-level questions.
    if (
        not confirm_key
        and _question_is_experiment_scoped(q)
        and not _active_experiment(app, ui_context)
    ):
        return _gate_response(
            q,
            "needs_experiment",
            "That's an experiment-level question, but no experiment is selected yet. "
            "Pick one from the **experiment dropdown** (or tell me which experiment), then "
            "ask again.",
            llm_loaded,
        )
    return None


def _llm_is_loaded(app) -> bool:
    if app.llm is not None and getattr(app.llm, "is_loaded", False):
        return True
    try:
        from continum.crosscutting.llm import llm_status

        return bool(llm_status().get("is_loaded", False))
    except Exception:
        return False


def _auto_mode(q: str) -> str:
    ql = q.lower()
    guide_kw = (
        "how do i",
        "how to",
        "what is persist",
        "what is continum",
        "what can you",
        "what can this",
        "what can i do",
        "what do you do",
        "capabilit",
        "guide",
        "help me",
        "use this",
        "what does this",
        "explain the",
        "where do i",
        "which module",
        "what module",
        "getting started",
        "tutorial",
        "navigate",
        "how does",
    )
    if any(k in ql for k in guide_kw):
        return "guide"
    data_kw = (
        "how many",
        "average",
        "avg",
        "sum ",
        "count",
        "total",
        " rate",
        "ior",
        "aov",
        "conversion",
        "segment",
        " per ",
        "trend",
        "top ",
        "highest",
        "lowest",
        "list ",
        "show me",
        "breakdown",
        "distribution",
        "revenue",
        "order value",
        "by ",
    )
    if any(k in ql for k in data_kw):
        return "data"
    return "copilot"


def _capability_summary() -> str:
    """A curated 'what can you do' overview built from the real tool catalog."""
    lines = [
        "**Continum Copilot — what I can do**",
        "",
        "Ask me in plain English about your experimentation dataset. I can:",
        "",
        "**📊 Answer data questions** (natural language → SQL): metrics like IOR, AOV and "
        "conversion; breakdowns by segment or platform; trends, top/bottom and comparisons.",
        "",
        "**🧪 Run experiment modules** — just ask for any of these:",
    ]
    try:
        from continum.orchestrator import MATCHVIEW_TOOLS

        for t in MATCHVIEW_TOOLS:
            desc = (t.description or "").rstrip(".")
            lines.append(f"- **{t.module_name}** — {desc}")
    except Exception:
        pass
    lines += [
        "",
        '**🧭 Guide you step by step** — say *"guide me"* or *"what should I do next"* '
        "to start the guided experimentation flow.",
        "",
        'Try: *"what\'s the current IOR?"* · *"run the readout for <experiment>"* · '
        '*"why did it drop?"* · *"is the experiment healthy?"*',
    ]
    return "\n".join(lines)


def _answer_guide(app, q: str, llm_loaded: bool) -> str:
    # Capability / "what can you do" questions get a curated overview of the actual
    # tools — far more useful than dumping README setup text.
    ql = (q or "").lower()
    if (
        ("what can" in ql and ("do" in ql or "help" in ql))
        or "capabilit" in ql
        or "what do you do" in ql
        or "what does this do" in ql
        or "who are you" in ql
        or "what are you" in ql
    ):
        return _capability_summary()
    # Otherwise: README-grounded help, served by the AskData engine's torch-free
    # README reader (works with or without the local ML stack) and the provider-
    # agnostic LLM (Azure/OpenAI if configured, else local fallback).
    from continum.askdata import get_askdata_engine

    return get_askdata_engine(app).about(q).get("response", "")


def _is_meta_q(q: str) -> bool:
    """Recommendation / session-summary questions — answered fast, no NL->SQL."""
    ql = (q or "").lower()
    return any(
        k in ql
        for k in (
            "what should i run next",
            "what to run next",
            "what next",
            "what should i do next",
            "what should i do",
            "what do you recommend",
            "recommend a next",
            "suggest a next",
            "next step",
            "next-step",
            "summarise this session",
            "summarize this session",
            "session summary",
            "summarise the session",
            "summarize the session",
            "summarise my session",
            "summarize my session",
        )
    )


def _session_summary(app) -> str:
    s = getattr(app, "ses", None)
    lines = ["**Session summary**", ""]
    try:
        if getattr(s, "active_experiment", None):
            lines.append(f"- Active experiment: **{s.active_experiment}**")
        metrics = getattr(s, "active_metrics", None) or []
        if metrics:
            lines.append(f"- Active metrics: {', '.join(list(metrics)[:5])}")
        hist = getattr(s, "execution_history", None) or []
        if hist:
            lines.append(f"- Modules run this session: {len(hist)}")
            for rec in hist[-6:]:
                icon = "✅" if getattr(rec, "ok", True) else "❌"
                lines.append(
                    f"  {icon} {getattr(rec, 'module', '?')} "
                    f"({(getattr(rec, 'elapsed_s', 0) or 0):.1f}s)"
                )
        else:
            lines.append("- No modules run yet this session.")
    except Exception:
        logger.exception("session summary failed")
    try:
        w, r = len(app.bus.warnings()), len(app.bus.recommendations())
        lines.append(f"- Intelligence: {w} warning(s), {r} recommendation(s)")
    except Exception:
        pass
    return "\n".join(lines)


def _answer_meta(app, q: str) -> str:
    """Instant deterministic answer for next-step / summary questions (no LLM)."""
    if "summar" in (q or "").lower():
        return _session_summary(app)
    try:
        from continum.askdata import flow as F  # guided-flow planner

        prog = F.locate(app.ses)
        return F.render_overview(prog, F.suggest_next(app.ses))
    except Exception:
        logger.exception("next-step planner failed")
        return (
            "Good next steps: run a **Campaign** readout to see the latest result, "
            "check **Sequence Monitoring** for experiment health, or run **Campaign "
            "Insights** (causal) to understand a change. Open the 🧭 guided flow for a "
            "step-by-step plan."
        )


def _module_run_redirect(app, q: str):
    """If the user asks to RUN a module that isn't one of the 6 quick tools, point
    them to the guided flow (which collects the module's inputs) rather than letting
    the request fall through to NL->SQL (which produces a wrong 'no data' essay).
    Gated on an explicit run-verb prefix so data questions are never hijacked."""
    ql = (q or "").lower().strip()
    if not any(ql.startswith(v) for v in ("run ", "start ", "execute ", "launch ", "do the ")):
        return None
    name = None
    try:
        from continum.askdata import flow as F

        mod = F.match_module(q, app.ses)
        if mod and mod != "askdata":
            name = mod.replace("_", " ").title()
    except Exception:
        pass
    if name is None:  # typo-tolerant net for the guided-flow-only modules
        for label, kws in (
            ("Opportunity Sizing", ("opportun", "oppurtun", "sizing", "sizeing", "size the")),
            ("Power Calculator", ("power calc", "sample size", " mde", "powered enough")),
            ("Learnings Repository", ("learning", "learnings")),
            ("KPI & Tracking Plan", ("tracking plan", "kpi")),
            ("Experiment Brief", ("experiment brief",)),
        ):
            if any(k in ql for k in kws):
                name = label
                break
    if name is None:
        return None
    return (
        f"**{name}** is an experiment module — run it from its **card on the dashboard**, "
        f"not from this chat. In the left sidebar open the matching phase (Opportunity "
        f"Sizing, Power Calculator, KPI & Tracking Plan and Experiment Brief live under "
        f"**Planning**), click the module's card to open its input form (monthly inquiries, "
        f"baseline rate, MDE, …), then run it.\n\n"
        f"_This chat answers data questions about your experiments — e.g. "
        f'"compare conversion by variant for mobile_nav_redesign"._'
    )


def _module_redirect_msg(app, module_name: str):
    """Guided-flow redirect for ANY registered module the LLM router picked to run.
    Unlike _module_run_redirect (keyword/prefix-gated, 5 modules), this works for
    every module in the dispatcher registry — it names the module and points the
    user at its dashboard card / input form."""
    if not module_name:
        return None
    label = module_name.replace("_", " ").title()
    desc = ""
    try:
        from continum.toolinterface import get_module

        spec = get_module(module_name)
        if spec is not None:
            desc = (spec.description or "").strip()
    except Exception:
        pass
    desc_line = f"\n\n_{desc}_" if desc else ""
    return (
        f"**{label}** is an experiment module — run it from its **card on the "
        f"dashboard**, not from this chat. In the left sidebar open the matching "
        f"phase, click the **{label}** card to open its input form, fill in the "
        f"inputs it needs, then run it.{desc_line}\n\n"
        f"_This chat answers data questions about your experiments — e.g. "
        f'"compare conversion by variant for mobile_nav_redesign"._'
    )


def _answer_data(app, q: str, ui_context: dict, llm_loaded: bool) -> dict:
    # AskData multi-agent LangGraph engine (NL → SQL → insight). Runs on
    # Azure/OpenAI when credentials are configured, else a local fallback model.
    # It builds its own in-memory SQLite from the bundled dataset (so it does
    # not depend on the live DuckDB) and answers "about itself" from the README.
    from continum.askdata import get_askdata_engine

    eng = get_askdata_engine(app)
    return eng.ask(q, ui_context=ui_context)


def _copilot_suggestions(app, q: str, mode: str) -> list:
    out: list = []
    try:
        from continum.intentanalyser import Intent, detect_intent

        follow = {
            Intent.SIGNIFICANCE: ["Why is it (not) significant?", "Show the segment breakdown"],
            Intent.WHY_DROPPED: ["Which segment drove the drop?", "Is there an SRM issue?"],
            Intent.WHY_IMPROVED: ["Which segment drove the lift?", "Is the result trustworthy?"],
            Intent.NEXT_STEP: ["What should I run next?", "Summarise this session"],
            Intent.SEGMENT_EXPLAIN: [
                "Compare the top and bottom segments",
                "Any Simpson's paradox?",
            ],
            Intent.CAUSAL_EXPLAIN: ["Run causal analysis", "How strong is the attribution?"],
            Intent.ANOMALY: ["Run the health monitor", "What changed in the last 24h?"],
        }.get(detect_intent(q), [])
        out += follow
    except Exception:
        pass
    if mode in ("data", "askdata"):
        try:
            from continum.askdata import get_metadata as _askdata_meta

            out += _askdata_meta().get("suggested_questions", [])[:3]
        except Exception:
            pass
    try:
        if app.ses and app.ses.recommendations:
            for r in app.ses.recommendations[:2]:
                out.append(f"How do I {r.action}?")
    except Exception:
        pass
    if not out:
        out = [
            "What can you do?",
            "What questions can I ask about the data?",
            "How do I use this tool?",
        ]
    seen, res = set(), []
    for s in out:
        if s and s not in seen:
            seen.add(s)
            res.append(s)
        if len(res) >= 5:
            break
    return res


def _maybe_readout_answer(app, q: str, force: bool = False):
    """If the question is about a readout (or `force` from an explicit readout
    action like the readout chips), return a grounded answer string; otherwise
    None so normal routing runs. With `force`, answers even with no saved outputs
    (readout.answer gives a friendly 'no readouts yet' message)."""
    try:
        from continum.askdata import readout as _readout

        if force or (_readout.get_store(app) and _readout.is_readout_question(q)):
            return _readout.answer(app, q).get("response", "")
    except Exception:
        logger.exception("readout answer failed")
    return None


@bp.route("/copilot/ask", methods=["POST"])
def copilot_ask():
    # MatchView tool-calling layer: detect a module intent → confirm → execute.
    from continum.orchestrator import (
        KIND_DATA,
        KIND_DEPLOY,
        confirmation_message,
        detect_tool,
        execute_tool,
        get_tool,
    )
    from continum.orchestrator import deploy_warning as _deploy_warning

    app = _app()
    body = request.get_json(silent=True) or {}
    q = (body.get("question") or "").strip()
    mode = (body.get("mode") or "auto").lower()
    ui_context = body.get("ui_context") or {}
    confirm_key = (body.get("confirm_tool") or "").strip()
    decline = bool(body.get("decline"))
    readout_q = bool(body.get("readout"))  # explicit "ask the readout" (readout chips)
    # Internal calls (KPI cards, portfolio widgets) reuse this endpoint but must
    # not be blocked by the selection gate — they report Xometry warehouse numbers.
    system_call = bool(body.get("system"))
    if not q:
        return jsonify({"error": "No question provided"}), 400

    if app.db is None:
        return jsonify(
            {
                "question": q,
                "mode": mode,
                "suggestions": [],
                "booting": True,
                "response": "I'm still loading the dataset — give me a moment and ask again.",
            }
        )

    llm_loaded = _llm_is_loaded(app)

    # ── 0) Selection gating — mirror the dataset/experiment dropdowns. Meta/help
    #        questions answer anytime; data questions require a dataset, and
    #        experiment-level questions require an experiment. Internal/system
    #        calls bypass the gate. ─────────────────────────────────────────────
    if not system_call:
        _gate = _selection_gate(app, q, ui_context, confirm_key, llm_loaded)
        if _gate is not None:
            return jsonify(_gate)

    sql = None
    table = []
    columns = []
    err = None
    viz = []
    deploy_warn = None
    next_steps = []

    # ── 1) User confirmed a MatchView module → execute it internally ─────────
    if confirm_key:
        tool = get_tool(confirm_key)
        if tool is None:
            response, err, resolved = "That action is no longer available.", "unknown_tool", "tool"
        elif (_co := _needs_experiment_callout(tool, app, ui_context)) is not None:
            # A7 — don't run an experiment-scoped module with no experiment selected.
            return jsonify(
                {
                    "question": q,
                    "response": _co,
                    "mode": "needs_experiment",
                    "sql": None,
                    "table": [],
                    "columns": [],
                    "visualizations": [],
                    "pending_tool": None,
                    "deploy_warning": None,
                    "next_steps": [],
                    "suggestions": [],
                    "llm_loaded": llm_loaded,
                    "error": None,
                }
            )
        else:
            try:
                out = execute_tool(app, tool, q, ui_context)
                response = out.get("response", "")
                sql, table = out.get("sql"), out.get("table", [])
                columns, err = out.get("columns", []), out.get("error")
                viz = out.get("visualizations", []) or []
                next_steps = list(tool.next_steps or [])
                if tool.kind == KIND_DEPLOY:
                    deploy_warn = _deploy_warning(tool)
                if sql or viz:
                    llm_loaded = True
                resolved = "tool:" + tool.key
            except Exception as e:
                logger.exception("tool execution failed")
                response, err = f"Sorry — the {tool.module_name} module hit an error: {e}", str(e)
                resolved = "tool"

    # ── 1b) Readout Q&A → grounded answer over the saved outputs. Wins over
    #        tool-detection when there are saved outputs and the question is
    #        ABOUT a readout (not a request to run one). ─────────────────────
    elif not decline and (_rd := _maybe_readout_answer(app, q, force=readout_q)) is not None:
        response, resolved = _rd, "readout"

    # ── 1c) Fast meta answers (no LLM): "what should I run next" / "summarise
    #        this session". These are recommendation/summary questions, not data
    #        questions — answer instantly from session state instead of a ~17s
    #        NL→SQL round-trip that just returned "No data available".
    elif not decline and mode in ("auto", "") and _is_meta_q(q):
        response, resolved = _answer_meta(app, q), "next-step"

    # ── 2/3) Tool / module / data / guide / meta — LLM-first, keyword fallback ──
    #   One structured LLM call (askrouter.llm_route) selects the action over the
    #   FULL tool catalog; it returns None when no LLM is configured / it abstains
    #   / it errors, in which case we fall back to the original keyword routers
    #   (detect_tool, _module_run_redirect, _auto_mode). The deterministic fast
    #   branches above (confirm / readout / meta-keyword) already returned, so the
    #   routing LLM call is only made when actually needed.
    else:
        try:
            from continum.askrouter import llm_route

            # A11 — faster pathing: an explicit keyword tool match (high precision,
            # e.g. "run the readout", "is it healthy", "deploy") needs no routing
            # LLM call at all. Only fall back to the structured LLM router when the
            # cheap keyword routers can't classify the request — this removes a
            # whole LLM round-trip from the common, explicit requests.
            kw_tool = detect_tool(q, ui_context) if mode in ("auto", "") else None
            route = (
                None
                if kw_tool is not None
                else (llm_route(app, q, ui_context) if mode in ("auto", "") else None)
            )

            # (a) MatchView tool → confirm first (keyword match wins, else LLM choice)
            tool = kw_tool or (
                get_tool(route["key"]) if (route and route.get("action") == "tool") else None
            )
            # A KIND_DATA tool's target IS the AskData engine — confirming it just
            # runs the same NL->SQL->viz path. Skip the pointless confirmation and
            # let the data question flow straight through AskData (which produces
            # the chart), instead of intercepting it with a "run <tool>?" prompt.
            if tool is not None and tool.kind == KIND_DATA:
                tool = None
            if tool is not None:
                pending = {
                    "key": tool.key,
                    "module_name": tool.module_name,
                    "kind": tool.kind,
                    "target": tool.target,
                    "description": (tool.description or "").strip(),
                }
                dw = _deploy_warning(tool) if tool.kind == KIND_DEPLOY else None
                try:
                    app.aud.record(
                        "copilot_confirm",
                        q[:60],
                        {"tool": tool.key},
                        session_id=app.ses.session_id if app.ses else "",
                    )
                except Exception:
                    pass
                return jsonify(
                    {
                        "question": q,
                        "response": confirmation_message(tool),
                        "mode": "confirm",
                        "sql": None,
                        "table": [],
                        "columns": [],
                        "visualizations": [],
                        "pending_tool": pending,
                        "deploy_warning": dw,
                        "next_steps": [],
                        "suggestions": [],
                        "llm_loaded": llm_loaded,
                        "error": None,
                    }
                )

            # (b) Run a specialised module → guided-flow redirect (LLM names any
            #     module; keyword fallback handles the prefix-gated cases).
            redirect = None
            if route and route.get("action") == "module":
                redirect = _module_redirect_msg(app, route.get("module"))
            if redirect is None and not decline and mode in ("auto", ""):
                redirect = _module_run_redirect(app, q)

            if redirect is not None:
                response, resolved = redirect, "module"
            else:
                # (c) guide / data / meta (LLM choice, else keyword _auto_mode)
                if decline:
                    # "No, just answer" → give a direct data-grounded answer, never
                    # a guide/meta detour or another tool confirm.
                    resolved = "data"
                elif route and route.get("action") in ("guide", "data", "meta"):
                    resolved = route["action"]
                else:
                    resolved = _auto_mode(q) if mode in ("auto", "") else mode
                if resolved == "meta":
                    response, resolved = _answer_meta(app, q), "next-step"
                elif resolved == "guide":
                    response = _answer_guide(app, q, llm_loaded)
                else:
                    d = _answer_data(app, q, ui_context, llm_loaded)
                    response = d.get("response", "")
                    sql, table = d.get("sql"), d.get("table", [])
                    columns, err = d.get("columns", []), d.get("error")
                    viz = d.get("visualizations", []) or []
                    if d.get("provider") in ("azure", "openai"):
                        llm_loaded = True
                    resolved = "askdata"
        except Exception as e:
            logger.exception("copilot_ask failed")
            response, err = f"Sorry — I ran into an error: {e}", str(e)
            resolved = "askdata"

    suggestions = next_steps or _copilot_suggestions(app, q, resolved)
    try:
        app.aud.record(
            "copilot_ask",
            q[:60],
            {"mode": resolved, "llm": llm_loaded},
            session_id=app.ses.session_id if app.ses else "",
        )
    except Exception:
        pass

    return jsonify(
        {
            "question": q,
            "response": response,
            "mode": resolved,
            "sql": sql,
            "table": table,
            "columns": columns,
            "visualizations": viz,
            "deploy_warning": deploy_warn,
            "next_steps": next_steps,
            "pending_tool": None,
            "suggestions": suggestions,
            "llm_loaded": llm_loaded,
            "error": err,
        }
    )


@bp.route("/copilot/metadata")
def copilot_metadata():
    # Describe the AskData engine's connected dataset (used to seed chips).
    try:
        from continum.askdata import get_active_dataset_name
        from continum.askdata import get_metadata as _askdata_meta
        from continum.askdata.llm import active_provider

        meta = _askdata_meta()
        tables = list((meta.get("column_descriptions") or {}).keys())
        return jsonify(
            {
                "domain_context": meta.get("domain_context"),
                "dataset": get_active_dataset_name(),
                "provider": active_provider(),
                "n_tables": len(tables),
                "tables": tables,
                "suggested_questions": meta.get("suggested_questions", []),
            }
        )
    except Exception as e:
        logger.exception("copilot_metadata failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/copilot/datasets")
def copilot_datasets():
    # List the AskData datasets available to switch between (data view + switcher).
    try:
        from continum.askdata.metadata import METADATA, get_display_name, list_datasets

        items = [
            {
                "name": n,
                "display_name": get_display_name(n),
                "domain_context": METADATA[n].get("domain_context", ""),
            }
            for n in list_datasets()
        ]
        # The active dataset for gating is the *session* selection (None until the
        # user picks one), not the AskData engine's env default.
        app = _app()
        active = getattr(getattr(app, "ses", None), "active_dataset", None)
        return jsonify({"active": active, "datasets": items})
    except Exception as e:
        logger.exception("copilot_datasets failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/copilot/dataset", methods=["POST"])
def copilot_set_dataset():
    # Switch the active AskData dataset by rebuilding the cached engine.
    import os

    from continum.askdata.engine import AskDataGraphEngine
    from continum.askdata.metadata import get_metadata, list_datasets

    app = _app()
    body = request.get_json(silent=True) or {}
    name = (body.get("dataset") or "").strip()
    if name not in list_datasets():
        return jsonify({"error": "unknown dataset: " + name}), 400
    # DuckDB-backed datasets need the booted warehouse — guard the boot race.
    if get_metadata(name).get("source") == "duckdb" and getattr(app, "db", None) is None:
        return jsonify({"error": "Experiment data is still loading — try again in a moment."}), 503
    try:
        os.environ["ACTIVE_DATASET"] = name
        app._askdata_graph = AskDataGraphEngine(dataset=name, db=getattr(app, "db", None))
        # Keep the session's gating state in sync with the AskData engine so the
        # chatbot knows a dataset/company is now selected.
        if getattr(app, "ses", None) is not None:
            app.ses.select_dataset(name)
            app.ses.save()
            if getattr(app, "aud", None) is not None:
                app.aud.record("select_dataset", name, session_id=app.ses.session_id)
    except Exception as e:
        logger.exception("dataset switch failed")
        return jsonify({"error": str(e)}), 500
    return jsonify({"active": name, "ok": True})


@bp.route("/copilot/portfolio")
def copilot_portfolio():
    """Portfolio summary for the Ask-AI / Copilot KPI cards: experiment count,
    headline metrics, and a *modeled* GMV/margin (there is no measured spend in
    the dataset, so "return" is real GMV and margin is a labeled 30% assumption).

    One aggregate pass over the live gold table — cheap enough to call on tab open.
    """
    app = _app()
    db = getattr(app, "db", None)
    if db is None:
        return jsonify({"booting": True})
    GROSS_MARGIN = 0.30
    ASSUMED_AOV = 500.0  # same baseline default the rest of the app uses when the
    # synthetic dataset carries no order_value (AOV resolves to 0)
    try:
        row = db.execute("""
            SELECT COUNT(DISTINCT experiment_name)                              AS n_experiments,
                   COUNT(*)                                                     AS n_inquiries,
                   AVG(CAST(converted_to_order AS DOUBLE))                      AS ior,
                   AVG(CASE WHEN converted_to_order = 1 THEN order_value END)   AS measured_aov,
                   SUM(CASE WHEN converted_to_order = 1 THEN COALESCE(order_value,0) ELSE 0 END) AS measured_gmv
            FROM gold_experiment_analysis
        """).fetchone()
        n_exp, n_inq, ior, measured_aov, measured_gmv = row
        n_inq = int(n_inq or 0)
        ior = float(ior or 0.0)
        measured_aov = float(measured_aov or 0.0)
        measured_gmv = float(measured_gmv or 0.0)
        converted_orders = round(n_inq * ior)

        # "return" = GMV. Prefer measured order value; fall back to a modeled figure
        # (converted orders × baseline AOV) when the data has no order value, so the
        # card is meaningful instead of $0. Flagged `modeled` so the UI can label it.
        aov_modeled = measured_aov <= 0.0
        eff_aov = ASSUMED_AOV if aov_modeled else measured_aov
        gmv = measured_gmv if measured_gmv > 0 else converted_orders * eff_aov

        out = {
            "n_experiments": int(n_exp or 0),
            "n_inquiries": n_inq,
            "ior": ior,
            "converted_orders": int(converted_orders),
            "aov": round(eff_aov, 2),
            "aov_modeled": aov_modeled,
            "total_gmv": round(gmv, 2),
            "gross_margin_rate": GROSS_MARGIN,
            "modeled_margin": round(gmv * GROSS_MARGIN, 2),
            "gmv_modeled": measured_gmv <= 0,  # GMV came from the AOV assumption
        }
        try:
            out["n_runs"] = len(getattr(app.ses, "execution_history", None) or [])
        except Exception:
            out["n_runs"] = 0
        return jsonify(out)
    except Exception as e:
        logger.exception("copilot_portfolio failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/copilot/data-preview")
def copilot_data_preview():
    # Sample rows from every table of the connected dataset (the data view).
    try:
        from continum.askdata import get_askdata_engine

        eng = get_askdata_engine(_app())
        return jsonify(eng.preview(limit=5))
    except Exception as e:
        logger.exception("copilot_data_preview failed")
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# SAVED OUTPUTS — the post-analysis flow: upload readouts (PDF/DOCX/text) and
# reference module-generated outputs; the Copilot answers grounded in them.
# ─────────────────────────────────────────────────────────────────────────────


@bp.route("/copilot/readouts")
def copilot_readouts():
    from continum.askdata import readout as R

    return jsonify({"readouts": R.list_readouts(_app())})


@bp.route("/copilot/readout/upload", methods=["POST"])
def copilot_readout_upload():
    from continum.askdata import readout as R

    app = _app()
    files = request.files.getlist("files")
    if not files and "file" in request.files:
        files = [request.files["file"]]
    if not files:
        return jsonify({"error": "No file uploaded"}), 400
    added = []
    for f in files:
        try:
            item = R.add_uploaded(app, f.filename or "readout", f.read())
            added.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "n_chars": item["n_chars"],
                    "source": item["source"],
                }
            )
        except Exception as e:
            logger.exception("readout upload failed for %s", getattr(f, "filename", "?"))
            added.append({"name": getattr(f, "filename", "?"), "error": str(e)})
    return jsonify(
        {
            "added": added,
            "count": len([a for a in added if not a.get("error")]),
            "readouts": R.list_readouts(app),
        }
    )


@bp.route("/copilot/readout/register", methods=["POST"])
def copilot_readout_register():
    # Register a finished run's generated outputs (PDF/text) as readouts.
    from continum.askdata import readout as R

    app = _app()
    body = request.get_json(silent=True) or {}
    run_id = (body.get("run_id") or "").strip()
    paths = app.stream_queues.get(f"files_{run_id}", []) if run_id else []
    added = []
    for p in paths:
        item = R.add_generated(app, p, run_id=run_id)
        if item:
            added.append({"id": item["id"], "name": item["name"], "n_chars": item["n_chars"]})
    return jsonify({"added": added, "count": len(added), "readouts": R.list_readouts(app)})


@bp.route("/copilot/readouts/clear", methods=["POST"])
def copilot_readouts_clear():
    from continum.askdata import readout as R

    n = R.clear(_app())
    return jsonify({"cleared": n, "readouts": []})


# ─────────────────────────────────────────────────────────────────────────────
# COPILOT — GUIDED FLOW (MVP2)
#   Proactive, stateful slot-filling over the module lifecycle: locate the user
#   from their run history, suggest the next step, ask one question per input
#   field, then hand the gathered kwargs to /api/execute. Conversation state is
#   a tiny dict round-tripped to the client, so this endpoint stays stateless
#   across turns. The per-module field schema reuses _get_module_config (the
#   same schema the config form uses), so questions and the form never drift.
# ─────────────────────────────────────────────────────────────────────────────


def _flow_reply(state: dict, config: dict, *, error: str = None, extra: dict = None):
    """Render a filling/confirm flow state into the chat payload."""
    from continum.askdata import flow as F

    if state.get("stage") == "filling":
        text, chips = F.format_question(state, config)
    elif state.get("stage") == "confirm":
        text, chips = F.format_confirm(state, config)
    else:
        text, chips = "", []
    if error:
        text = f"⚠️ {error}\n\n{text}"
    payload = {
        "response": text,
        "stage": state.get("stage"),
        "flow_state": state,
        "chips": chips,
        "action": None,
        "module_key": state.get("module_key"),
    }
    if extra:
        payload.update(extra)
    return jsonify(payload)


@bp.route("/copilot/flow", methods=["POST"])
def copilot_flow():
    from continum.askdata import flow as F

    app = _app()
    body = request.get_json(silent=True) or {}
    msg = (body.get("message") or "").strip()
    st = body.get("flow_state") or None
    uic = body.get("ui_context") or {}

    if app.db is None:
        return jsonify(
            {
                "response": "I'm still loading the dataset — give me a moment and try again.",
                "stage": "idle",
                "flow_state": None,
                "chips": [],
                "action": None,
                "booting": True,
            }
        )

    ses = app.ses
    active_exp = uic.get("active_experiment") or (ses.active_experiment if ses else "") or ""

    def _overview(note: str = ""):
        prog = F.locate(ses)
        sugg = F.suggest_next(ses)
        text = F.render_overview(prog, sugg)
        if note:
            text = note + "\n\n" + text
        chips = [{"label": s["label"], "value": s["module_key"]} for s in sugg]
        chips.append({"label": "💬 Ask a data question", "value": "askdata"})
        return jsonify(
            {
                "response": text,
                "stage": "choosing",
                "flow_state": {"stage": "choosing"},
                "chips": chips,
                "action": None,
                "progress": prog["line"],
            }
        )

    try:
        # (Re)start → overview + next-step suggestions.
        if not st or F.is_restart(msg):
            return _overview()

        stage = st.get("stage")

        # ── Pick a step ──────────────────────────────────────────────────────
        if stage == "choosing":
            mod = F.match_module(msg, ses)
            if mod == "askdata":
                return jsonify(
                    {
                        "response": "Sure — ask your data question and I'll query the dataset "
                        "(NL→SQL). Switch the pane to **Data** mode for chart output.",
                        "stage": "choosing",
                        "flow_state": {"stage": "choosing"},
                        "chips": [],
                        "action": None,
                    }
                )
            if not mod:
                return _overview("I didn't catch which step you meant — pick one:")
            cfg = _get_module_config(mod, app.db)
            return _flow_reply(F.init_slots(mod, cfg, active_exp), cfg)

        # ── Fill one input slot per turn ─────────────────────────────────────
        if stage == "filling":
            mod = st.get("module_key")
            cfg = _get_module_config(mod, app.db)
            new_state, err = F.record_answer(st, msg, cfg)
            return _flow_reply(new_state, cfg, error=err)

        # ── Confirm → hand off to execution ──────────────────────────────────
        if stage == "confirm":
            mod = st.get("module_key")
            low = msg.strip().lower()
            if low == "__edit__" or "start over" in low or low == "edit":
                cfg = _get_module_config(mod, app.db)
                return _flow_reply(F.init_slots(mod, cfg, active_exp), cfg)
            if low == "__cancel__" or F.is_no(msg):
                return _overview("No problem — cancelled that step.")
            if F.is_yes(msg) or "run" in low:
                cfg = _get_module_config(mod, app.db)
                title = cfg.get("title", F.module_label(mod))
                fields = F.run_fields(st)
                try:
                    app.aud.record(
                        "copilot_flow_run",
                        mod,
                        {"fields": list(fields.keys())},
                        session_id=ses.session_id if ses else "",
                    )
                except Exception:
                    pass
                return jsonify(
                    {
                        "response": f"▶ Running **{title}** — results will stream in the console below.",
                        "stage": "running",
                        "flow_state": None,
                        "chips": [],
                        "action": "run_module",
                        "module_key": mod,
                        "fields": fields,
                    }
                )
            cfg = _get_module_config(mod, app.db)
            return _flow_reply(st, cfg, error="Please choose Run, Start over, or Cancel.")

        return _overview()
    except Exception as e:
        logger.exception("copilot_flow failed")
        return jsonify(
            {
                "response": f"Sorry — the guided flow hit an error: {e}",
                "stage": "idle",
                "flow_state": None,
                "chips": [],
                "action": None,
                "error": str(e),
            }
        )
