from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

# Keys auto-injected by _build_default_kwargs that most pipeline functions don't accept.
# Applied universally to all module lambdas.
_STRIP_KEYS = {
    "baseline_ior", "ior", "current_ior", "aov", "daily_inquiries",
    "monthly_inquiries", "daily_eligible_traffic", "session_id", "client_name",
    "gross_margin", "horizon", "target_ior", "avg_aov", "category",
    "experiment_type", "maturity", "action", "query", "select experiment",
    "method_choice",
    # power_calculator labels
    "Baseline conversion/IOR rate (0-1)",
    "MDE — minimum detectable effect (% relative, e.g. 10)",
    "Significance level α", "Statistical power 1-β",
    "Number of variants (including control)",
    "Daily eligible traffic", "Fraction of traffic in experiment (0-1)",
}
def _ck(kw): return {k: v for k, v in kw.items() if k not in _STRIP_KEYS}


logger = logging.getLogger("continum.dispatcher")


# ─────────────────────────────────────────────────────────────────────────────
# MODULE SPEC
# ─────────────────────────────────────────────────────────────────────────────

class ModuleSpec:
    def __init__(self, name: str, fn: Callable, phase: str,
                 subsystem: str, description: str = "",
                 requires_db: bool = True, requires_llm: bool = False):
        self.name         = name
        self.fn           = fn
        self.phase        = phase
        self.subsystem    = subsystem
        self.description  = description
        self.requires_db  = requires_db
        self.requires_llm = requires_llm


_REGISTRY: Dict[str, ModuleSpec] = {}


def register_module(spec: ModuleSpec) -> None:
    _REGISTRY[spec.name] = spec


def list_modules() -> List[Dict]:
    _build_registry()
    # Skip non-module sentinel keys (e.g. "_intelligence_registered" guard flags).
    specs = [s for k, s in _REGISTRY.items()
             if not k.startswith("_") and isinstance(s, ModuleSpec)]
    return [
        {"name": s.name, "phase": s.phase, "description": s.description,
         "requires_db": s.requires_db, "requires_llm": s.requires_llm}
        for s in sorted(specs, key=lambda x: (x.phase, x.name))
    ]


def get_module(name: str) -> Optional[ModuleSpec]:
    _build_registry()
    return _REGISTRY.get(name)


def run_module(name: str = None, state=None, llm=None, db=None, **kwargs) -> Any:
    if name is None:
        name = kwargs.pop("module", None)
    if name is None:
        raise ValueError("Module name required — pass as first positional arg or module=")
    _build_registry()
    spec = _REGISTRY.get(name)
    if spec is None:
        raise ValueError(f"Unknown module: {name!r}. Available: {list(_REGISTRY)}")

    import time
    t0 = time.monotonic()
    try:
        result = spec.fn(state=state, llm=llm, db=db, **kwargs)
        elapsed = time.monotonic() - t0

        # Publish to InsightBus (non-fatal — never break the module run)
        try:
            from continum.insights.insight_bus import get_bus, publish_next_steps
            bus = get_bus()
            bus.success(name, f"{name} completed in {elapsed:.2f}s")
            publish_next_steps(name, bus)
        except Exception:
            pass

        return result
    except Exception:
        elapsed = time.monotonic() - t0
        try:
            from continum.insights.insight_bus import get_bus
            get_bus().warn(name, f"{name} failed after {elapsed:.2f}s")
        except Exception:
            pass
        raise


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRY BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _build_registry() -> None:
    if _REGISTRY:
        return

    # ── Phase 0 — Foundation ─────────────────────────────────────────────────

    try:
        from continum.contextmate.discovery import (
            run_schema_discovery, run_data_validation, run_dimension_setup,
        )
        register_module(ModuleSpec(
            "schema_discovery", lambda state, llm=None, db=None, **kw:
                run_schema_discovery(llm=llm, db=db, **_ck(kw)),
            "phase_0", "discovery",
            "Auto-generate CLIENT_SCHEMA from warehouse catalog.",
            requires_llm=True,
        ))
        register_module(ModuleSpec(
            "data_validation", lambda state, llm=None, db=None, **kw:
                run_data_validation(db=db, llm=llm),
            "phase_0", "validation",
            "Completeness, type, constraint, and business-rule checks.",
        ))
        register_module(ModuleSpec(
            "dimension_setup", lambda state, llm=None, db=None, **kw:
                run_dimension_setup(db=db, llm=llm),
            "phase_0", "setup",
            "Auto-detect segments, platforms, categories from data.",
        ))
    except ImportError as e:
        logger.debug("Phase 0 discovery modules unavailable: %s", e)

    try:
        from continum.experimentation.monitoring.monitors import PipelineHealthMonitor, WatchtowerMonitor
        register_module(ModuleSpec(
            "pipeline_health", lambda state, llm=None, db=None, **kw:
                PipelineHealthMonitor(db=db).run(),
            "phase_0", "monitoring",
            "Daily 5-check anomaly scan on Silver tables.",
        ))
        register_module(ModuleSpec(
            "watchtower", lambda state, llm=None, db=None, **kw:
                WatchtowerMonitor(db=db).run(),
            "phase_0", "monitoring",
            "Dimensional metric × slice anomaly scan.",
        ))
    except ImportError as e:
        logger.debug("Monitoring modules unavailable: %s", e)

    # ── Phase 1 — Planning ────────────────────────────────────────────────────

    try:
        from continum.experimentation.planning import (
            run_power_calculator, run_opportunity_sizing,
            run_audience_selection, run_brief_generator,
            run_metrics_and_tracking,
        )
        register_module(ModuleSpec(
            "power_calculator", lambda state, llm=None, db=None, **kw:
                run_power_calculator(llm=llm, db=db, **_ck(kw)),
            "phase_1", "planning",
            "Interactive sample-size and duration calculator with sensitivity analysis.",
        ))
        register_module(ModuleSpec(
            "opportunity_sizing", lambda state, llm=None, db=None, **kw:
                run_opportunity_sizing(llm=llm, db=db, **_ck(kw)),
            "phase_1", "planning",
            "Revenue upside from closing the IOR gap.",
        ))
        register_module(ModuleSpec(
            "audience_selection", lambda state, llm=None, db=None, **kw:
                run_audience_selection(llm=llm, db=db, **_ck(kw)),
            "phase_1", "planning",
            "Propensity-scored audience selection with inclusion/exclusion criteria.",
        ))
        register_module(ModuleSpec(
            "brief_generator", lambda state, llm=None, db=None, **kw:
                run_brief_generator(llm=llm, db=db, **_ck(kw)),
            "phase_1", "planning",
            "5-section experiment brief with hypothesis, metrics, audience, PDF output.",
            requires_llm=True,
        ))
        register_module(ModuleSpec(
            "metrics_and_tracking", lambda state, llm=None, db=None, **kw:
                run_metrics_and_tracking(llm=llm, db=db, **_ck(kw)),
            "phase_1", "planning",
            "KPI + tracking events plan with PDF output.",
            requires_llm=True,
        ))
    except ImportError as e:
        logger.debug("Phase 1 planning modules unavailable: %s", e)

    # ── Phase 2 — Live Monitoring ─────────────────────────────────────────────

    try:
        from continum.experimentation.monitoring.monitoring import run_health_monitor, run_sequential_testing
        register_module(ModuleSpec(
            "health_monitor", lambda state, llm=None, db=None, **kw:
                run_health_monitor(llm=llm, db=db, **_ck(kw)),
            "phase_2", "monitoring",
            "SRM, guardrails, IOR trajectory, ETA to significance.",
        ))
        register_module(ModuleSpec(
            "sequential_testing", lambda state, llm=None, db=None, **kw:
                run_sequential_testing(llm=llm, db=db, **_ck(kw)),
            "phase_2", "sequential",
            "mSPRT always-valid p-values — safe to peek at any time.",
        ))
    except ImportError as e:
        logger.debug("Phase 2 monitoring modules unavailable: %s", e)

    # ── Phase 2.5 — Post-Experiment Core (A/B readout) ────────────────────────

    try:
        from continum.experimentation.analysis_dag import run_experiment_analysis_pipeline

        def _run_post_exp(state, llm=None, db=None,
                          experiment_id: str = "", experiment_name: str = "", **kw):
            return run_experiment_analysis_pipeline(
                experiment_id=experiment_id,
                experiment_name=experiment_name or experiment_id,
                db=db, llm=llm,
                knowledge_graph=getattr(
                    getattr(state, "org", None), "_kg", None) if state else None,
                **_ck(kw),
            )

        register_module(ModuleSpec(
            "experiment_analysis", _run_post_exp,
            "phase_2", "analysis",
            "Full A/B readout pipeline: primary, segments, causal, narrative.",
        ))
    except ImportError as e:
        logger.debug("Experiment analysis pipeline unavailable: %s", e)

    # ── Phase 3 — Post-Experiment Deep Dive ──────────────────────────────────

    try:
        from continum.experimentation.post_analysis.analysis import (
            run_causal_analysis, run_pre_post_analysis,
            run_simpsons_paradox_detector, run_roi_tracker,
            run_learnings_repository,
        )
        register_module(ModuleSpec(
            "causal_analysis", lambda state, llm=None, db=None, **kw:
                run_causal_analysis(llm=llm, db=db, **_ck(kw)),
            "phase_3", "causal",
            "7-method causal analysis menu: DiD, ITS, PSM, RDD, SC, ARIMA, BSTS.",
        ))
        register_module(ModuleSpec(
            "pre_post_analysis", lambda state, llm=None, db=None, **kw:
                run_pre_post_analysis(llm=llm, db=db, **_ck(kw)),
            "phase_3", "analysis",
            "Pre-post analysis for 100% rollouts (weak causal claim).",
        ))
        register_module(ModuleSpec(
            "simpsons_paradox", lambda state, llm=None, db=None, **kw:
                run_simpsons_paradox_detector(llm=llm, db=db, **_ck(kw)),
            "phase_3", "analysis",
            "Detect when segment-level effects contradict overall direction.",
        ))
        register_module(ModuleSpec(
            "roi_tracker", lambda state, llm=None, db=None, **kw:
                run_roi_tracker(llm=llm, db=db, **_ck(kw)),
            "phase_3", "roi",
            "Post-ship OLS counterfactual to measure incremental GMV.",
        ))
        register_module(ModuleSpec(
            "learnings_repository", lambda state, llm=None, db=None, **kw:
                run_learnings_repository(llm=llm, db=db, **_ck(kw)),
            "phase_3", "knowledge",
            "Add, search, and browse experiment learnings. Persists in DuckDB.",
        ))
    except ImportError as e:
        logger.debug("Phase 3 analysis modules unavailable: %s", e)

    try:
        from continum.experimentation.monitoring.monitors import SequentialTester

        def _run_seq_tester(state, llm=None, db=None, **kw):
            tester = SequentialTester()
            return tester.run(db=db, **kw)

        register_module(ModuleSpec(
            "sequential_tester_core", _run_seq_tester,
            "phase_3", "sequential",
            "Core SequentialTester class (wire with experiment data).",
        ))
    except ImportError:
        pass

    # ── Phase 4 — Deploy ─────────────────────────────────────────────────────

    try:
        from continum.experimentation.deployment import run_uplift_modeller, run_decision_engine
        register_module(ModuleSpec(
            "uplift_modeller", lambda state, llm=None, db=None, **kw:
                run_uplift_modeller(llm=llm, db=db, **_ck(kw)),
            "phase_4", "deploy",
            "T-learner individual causal effect estimation. Registers uplift_scores.",
        ))
        register_module(ModuleSpec(
            "decision_engine", lambda state, llm=None, db=None, **kw:
                run_decision_engine(llm=llm, db=db, **_ck(kw)),
            "phase_4", "deploy",
            "Budget-constrained targeting optimisation using uplift scores.",
        ))
    except ImportError as e:
        logger.debug("Phase 4 deploy modules unavailable: %s", e)

    n = len(_REGISTRY)
    logger.info("Module registry built: %d modules registered", n)


__all__ = ["run_module", "list_modules", "get_module", "register_module",
           "ModuleSpec", "_build_registry"]


# ─────────────────────────────────────────────────────────────────────────────
# PATCH: append new Intelligence + Forecasting modules to _build_registry
# This block is appended after the original _build_registry definition.
# ─────────────────────────────────────────────────────────────────────────────

_ORIGINAL_BUILD_REGISTRY = _build_registry  # save original


def _build_registry() -> None:
    _ORIGINAL_BUILD_REGISTRY()

    # Guard: only run once (original already has an early-return if _REGISTRY non-empty,
    # but since we replaced _build_registry the guard is here)
    if _REGISTRY.get("_intelligence_registered"):
        return
    _REGISTRY["_intelligence_registered"] = True   # sentinel (not a real module)

    # ── Intelligence synthesis modules ─────────────────────────────────────────
    try:
        from continum.experimentation.post_analysis.synthesis import (
            run_kpi_synthesis,
            run_guardrail_generation,
            run_tracking_plan,
            run_historical_learning_retrieval,
            run_next_step_generation,
            run_anomaly_synthesis,
            run_cross_experiment_learning,
        )
        register_module(ModuleSpec(
            "kpi_synthesis",
            lambda state, llm=None, db=None, **kw: run_kpi_synthesis(llm=llm, db=db, **_ck(kw)),
            "intelligence", "kpi",
            "Infer and rank KPIs from live data distribution and experiment type.",
        ))
        register_module(ModuleSpec(
            "guardrail_generation",
            lambda state, llm=None, db=None, **kw: run_guardrail_generation(llm=llm, db=db, **_ck(kw)),
            "intelligence", "guardrails",
            "Generate data-driven guardrail thresholds from historical distributions.",
        ))
        register_module(ModuleSpec(
            "tracking_plan",
            lambda state, llm=None, db=None, **kw: run_tracking_plan(llm=llm, db=db, **_ck(kw)),
            "intelligence", "tracking",
            "Generate event tracking plan: names, properties, validation queries.",
        ))
        register_module(ModuleSpec(
            "historical_learning",
            lambda state, llm=None, db=None, **kw: run_historical_learning_retrieval(llm=llm, db=db, **_ck(kw)),
            "intelligence", "knowledge",
            "Semantic search + synthesis over all recorded experiment learnings.",
        ))
        register_module(ModuleSpec(
            "next_step_generation",
            lambda state, llm=None, db=None, **kw: run_next_step_generation(llm=llm, db=db, **_ck(kw)),
            "intelligence", "planning",
            "Context-aware next-step recommendations based on session state.",
        ))
        register_module(ModuleSpec(
            "anomaly_synthesis",
            lambda state, llm=None, db=None, **kw: run_anomaly_synthesis(llm=llm, db=db, **_ck(kw)),
            "intelligence", "monitoring",
            "Synthesise anomalies across metrics into a unified alert summary.",
        ))
        register_module(ModuleSpec(
            "cross_experiment_learning",
            lambda state, llm=None, db=None, **kw: run_cross_experiment_learning(llm=llm, db=db, **_ck(kw)),
            "intelligence", "knowledge",
            "Compare all experiments — win rates, patterns, portfolio synthesis.",
        ))
        logger.info("Intelligence synthesis modules registered")
    except ImportError as e:
        logger.debug("Intelligence synthesis modules unavailable: %s", e)

    # ── Forecasting modules ───────────────────────────────────────────────────
    try:
        from continum.experimentation.causal.forecasting import (
            run_arima_forecast, run_sarima_forecast,
            run_bsts_forecast, run_ets_forecast,
            run_forecast_ensemble, run_causal_impact,
        )

        def _run_forecasting(state, llm=None, db=None,
                             experiment_name: str = "",
                             horizon: int = 30,
                             method: str = "ensemble", **kw):
            if db is None:
                return {"error": "no_db"}
            try:
                df = db.execute("""
                    SELECT DATE_TRUNC('day', created_at) AS date,
                           AVG(CAST(converted_to_order AS DOUBLE)) AS ior
                    FROM silver_inquiries
                    GROUP BY 1 ORDER BY 1
                """).df()
                if len(df) < 10:
                    return {"error": "insufficient_data"}
                import pandas as pd
                series = pd.Series(df["ior"].values,
                                   index=pd.to_datetime(df["date"]))
                return run_forecast_ensemble(series, horizon=horizon, metric="IOR")
            except Exception as e:
                return {"error": str(e)}

        register_module(ModuleSpec(
            "forecasting",
            _run_forecasting,
            "phase_3", "forecasting",
            "Forecast IOR/volume via ARIMA + SARIMA + BSTS + ETS ensemble.",
        ))
        logger.info("Forecasting module registered")
    except ImportError as e:
        logger.debug("Forecasting modules unavailable: %s", e)

    # ── ROI Synthesis ─────────────────────────────────────────────────────────
    try:
        from continum.experimentation.analytics.roi_synthesis import run_roi_synthesis

        def _run_roi_synthesis_module(state, llm=None, db=None,
                                      experiment_name: str = "",
                                      ship_date: str = "", **kw):
            if db is None:
                return {"error": "no_db"}
            try:
                df = db.execute("""
                    SELECT created_at, converted_to_order, COALESCE(order_value, 0) AS order_value
                    FROM silver_inquiries
                """).df()
                if not ship_date:
                    import pandas as pd
                    mid = pd.to_datetime(df["created_at"]).median()
                    ship_date = str(mid.date())
                return run_roi_synthesis(df=df, ship_date=ship_date,
                                         experiment_name=experiment_name, **kw)
            except Exception as e:
                return {"error": str(e)}

        register_module(ModuleSpec(
            "roi_synthesis",
            _run_roi_synthesis_module,
            "phase_3", "roi",
            "OLS counterfactual + DiD projection → incremental GMV with CI.",
        ))
        logger.info("ROI synthesis module registered")
    except ImportError as e:
        logger.debug("ROI synthesis module unavailable: %s", e)

    n = len([k for k in _REGISTRY if not k.startswith("_")])
    logger.info("Extended registry: %d total modules", n)


# ─────────────────────────────────────────────────────────────────────────────
# V2 PATCH: Register all ported notebook analytical modules
# ─────────────────────────────────────────────────────────────────────────────

_V2_REGISTERED = False
_ORIGINAL_V2   = _build_registry  # save whatever _build_registry is at this point


def _build_registry() -> None:
    global _V2_REGISTERED
    _ORIGINAL_V2()
    if _V2_REGISTERED:
        return
    _V2_REGISTERED = True

    # ── Full causal analysis (engine.py — all 7 methods) ────────────────────
    try:
        from continum.experimentation.post_analysis.causal import run_causal_analysis_full
        register_module(ModuleSpec(
            "causal_analysis_full",
            lambda state, llm=None, db=None, **kw: run_causal_analysis_full(llm=llm, db=db, **_ck(kw)),
            "phase_3", "causal",
            "7-method causal engine: DiD v2 (bootstrap+event study+TWFE), ITS, PSM+Love plot, "
            "Synthetic Control v2, Mediation, RDD, Simpson's paradox detector.",
        ))
        logger.info("Registered causal_analysis_full")
    except ImportError as e:
        logger.debug("causal_analysis_full unavailable: %s", e)

    # ── Balance diagnostics ──────────────────────────────────────────────────
    try:
        from continum.experimentation.causal.balance import run_balance_battery, plot_love_plot, print_balance_report

        def _run_balance(state, llm=None, db=None, **kw):
            if db is None:
                return {"error": "no_db"}
            try:
                df = db.execute("SELECT * FROM gold_experiment_analysis LIMIT 50000").df()
                results = run_balance_battery(df, control_col="variant")
                n_ctrl = int((df["variant"] == "control").sum())
                n_trt  = int((df["variant"] != "control").sum())
                print_balance_report(results, n_ctrl, n_trt)
                love_path = plot_love_plot(results)
                return {"balance": results, "love_plot": love_path}
            except Exception as ex:
                return {"error": str(ex)}

        register_module(ModuleSpec(
            "balance_diagnostics",
            _run_balance,
            "phase_1", "design",
            "Covariate balance battery + Love plot for experiment assignment validation.",
        ))
    except ImportError as e:
        logger.debug("balance_diagnostics unavailable: %s", e)

    # ── Distribution shift detection ─────────────────────────────────────────
    try:
        from continum.experimentation.causal.engine import detect_distribution_shift

        def _run_shift(state, llm=None, db=None, **kw):
            if db is None:
                return {"error": "no_db"}
            try:
                import pandas as pd
                df_all = db.execute("SELECT * FROM silver_inquiries").df()
                df_all["created_at"] = pd.to_datetime(df_all["created_at"])
                mid     = df_all["created_at"].median()
                pre     = df_all[df_all["created_at"] < mid]
                post    = df_all[df_all["created_at"] >= mid]
                result  = detect_distribution_shift(pre, post)
                print(f"\n  Distribution shift: {result['n_shifted']}/{result['n_columns']} "
                      f"columns shifted (severity: {result['overall_severity']})")
                for col in result.get("shifted_columns", [])[:6]:
                    print(f"    ⚠️  {col['column']:<24} {col['test']:<5} p={col['p_value']:.4f}")
                return result
            except Exception as ex:
                return {"error": str(ex)}

        register_module(ModuleSpec(
            "distribution_shift",
            _run_shift,
            "phase_0", "validation",
            "Detect covariate distribution shifts (KS + chi²) between experiment periods.",
        ))
    except ImportError as e:
        logger.debug("distribution_shift unavailable: %s", e)

    # ── Opportunity sizing (funnel taxonomy) ─────────────────────────────────
    try:
        from continum.experimentation.analytics.opportunity import (
            pull_baselines, recommend_mde, compute_dynamic_opportunity,
            classify_feature, FUNNEL_TAXONOMY,
        )

        def _run_opp(state, llm=None, db=None,
                     description="", category="conversion", **kw):
            baselines = pull_baselines(db)
            cat       = classify_feature(description, llm) if description else category
            p_metric  = FUNNEL_TAXONOMY.get(cat, {}).get("primary_metric", "ior")
            baseline_rate = baselines.get(p_metric, baselines.get("ior", 0.18))
            mde_info  = recommend_mde(baseline_rate, cat, baselines)
            answers   = {**baselines, "_mde": mde_info, "horizon": kw.get("horizon", 12),
                         "gross_margin": kw.get("gross_margin", 0.30)}
            result    = compute_dynamic_opportunity(cat, answers)
            print(f"\n  Category       : {result['label']}")
            print(f"  Recommended MDE: {mde_info['recommended_rel_pct']:+.1f}% rel = "
                  f"{mde_info['recommended_abs']*100:+.3f}pp abs")
            print(f"  12-month GMV   : ${result['12m_gmv']:,.0f}")
            print(f"  12-month GM    : ${result['12m_gm']:,.0f}")
            return result

        register_module(ModuleSpec(
            "opportunity_sizing_v2",
            _run_opp,
            "phase_1", "planning",
            "Dynamic opportunity sizing: funnel taxonomy + data-driven MDE + incremental GMV chain.",
        ))
    except ImportError as e:
        logger.debug("opportunity_sizing_v2 unavailable: %s", e)

    # ── Analytics-grounded ask engine ────────────────────────────────────────
    try:
        from continum.askdata import run_ask
        register_module(ModuleSpec(
            "ask_v2",
            lambda state, llm=None, db=None, **kw: run_ask(
                llm=llm, db=db, session=state, **_ck(kw)),
            "intelligence", "ask",
            "Analytics-grounded ask — intent detection, live DB retrieval, "
            "bus context, LLM synthesis.",
            requires_llm=False,  # works without LLM (deterministic fallback)
        ))
    except ImportError as e:
        logger.debug("ask_v2 unavailable: %s", e)

    # ── Adaptive recommendations ─────────────────────────────────────────────
    try:
        from continum.experimentation.analytical_reasoning import adaptive_recommendations

        def _run_adaptive(state, llm=None, db=None, **kw):
            signals = kw.get("signals", {})
            result  = kw.get("result", None)
            recs    = adaptive_recommendations(result=result, signals=signals, llm=llm)
            print(f"\n  Adaptive recommendations ({len(recs)}):")
            for r in recs:
                print(f"    [{r.get('priority','?')}] {r['action']}")
                print(f"       {r['reason']}")
            return {"recommendations": recs}

        register_module(ModuleSpec(
            "adaptive_recommendations",
            _run_adaptive,
            "intelligence", "planning",
            "Context-aware next actions grounded in experiment results and live signals.",
        ))
    except ImportError as e:
        logger.debug("adaptive_recommendations unavailable: %s", e)

    # ── Open question generation ─────────────────────────────────────────────
    try:
        from continum.experimentation.analytical_reasoning import generate_open_questions

        def _run_open_q(state, llm=None, db=None,
                         experiment_name="", **kw):
            result = kw.get("result", {})
            qs = generate_open_questions(experiment_name, result, llm=llm)
            print(f"\n  Open questions for '{experiment_name}':")
            for i, q in enumerate(qs, 1):
                print(f"    {i}. {q}")
            return {"questions": qs}

        register_module(ModuleSpec(
            "open_questions",
            _run_open_q,
            "intelligence", "reasoning",
            "Generate follow-up analytical questions grounded in experiment results.",
        ))
    except ImportError as e:
        logger.debug("open_questions unavailable: %s", e)

    # ── Root-cause synthesis ─────────────────────────────────────────────────
    try:
        from continum.experimentation.analytical_reasoning import generate_root_cause

        def _run_root_cause(state, llm=None, db=None,
                             experiment_name="", **kw):
            anomalies = kw.get("anomalies", [])
            if not anomalies and db is not None:
                # Pull current anomalies from anomaly_synthesis
                try:
                    from continum.experimentation.post_analysis.synthesis import run_anomaly_synthesis
                    result   = run_anomaly_synthesis(db=db, llm=None, experiment_name=experiment_name)
                    anomalies = result.get("anomalies", [])
                except Exception:
                    pass
            rc = generate_root_cause(anomalies, experiment=experiment_name, llm=llm)
            print(f"\n  Root-cause synthesis:\n  {rc}\n")
            return {"root_cause": rc, "anomalies": anomalies}

        register_module(ModuleSpec(
            "root_cause",
            _run_root_cause,
            "intelligence", "monitoring",
            "Root-cause hypothesis generation from anomalies + pipeline context.",
        ))
    except ImportError as e:
        logger.debug("root_cause unavailable: %s", e)

    n_total = len([k for k in _REGISTRY if not k.startswith("_")])
    logger.info("V2 registry complete: %d total modules", n_total)


# ─────────────────────────────────────────────────────────────────────────────
# V3 PATCH: Swap thin module wrappers for full autonomous implementations
# ─────────────────────────────────────────────────────────────────────────────

_V3_REGISTERED = False
_PREV_V3_BUILD  = _build_registry


def _build_registry() -> None:
    global _V3_REGISTERED
    _PREV_V3_BUILD()
    if _V3_REGISTERED:
        return
    _V3_REGISTERED = True

    # ── Re-register Phase 1 with full autonomous implementations ──────────────
    try:
        from continum.experimentation.planning import (
            run_power_calculator, run_opportunity_sizing,
            run_brief_generator, run_metrics_and_tracking,
            run_audience_selection,
        )
        for name, fn, phase, cat, desc in [
            ("power_calculator",   run_power_calculator,   "phase_1", "planning",
             "Sample size + duration + power curve + PDF. Fully autonomous from live baselines."),
            ("opportunity_sizing", run_opportunity_sizing, "phase_1", "planning",
             "Dynamic funnel-taxonomy opportunity sizing + MDE recommendation + PDF."),
            ("brief_generator",    run_brief_generator,    "phase_1", "planning",
             "Experiment brief generator — auto-infers constraints, past learnings, PDF output."),
            ("metrics_and_tracking", run_metrics_and_tracking, "phase_1", "planning",
             "KPI synthesis + tracking plan + guardrails + PDF report."),
            ("audience_selection", run_audience_selection, "phase_1", "planning",
             "Propensity-based audience assignment + balance diagnostics + CSV output."),
        ]:
            _REGISTRY.pop(name, None)
            register_module(ModuleSpec(name, lambda state, llm=None, db=None, _fn=fn, **kw:
                _fn(llm=llm, db=db, **{k: v for k, v in kw.items() if k not in _STRIP_KEYS}), phase, cat, desc))
        logger.info("V3: Phase 1 modules re-registered")
    except ImportError as e:
        logger.debug("V3 Phase 1 import failed: %s", e)

    # ── Re-register Phase 2 ────────────────────────────────────────────────────
    try:
        from continum.experimentation.monitoring.monitoring import (
            run_health_monitor, run_sequential_testing,
        )
        for name, fn, desc in [
            ("health_monitor",    run_health_monitor,
             "SRM + guardrails + trajectory + ETA. Charts + PDF. Fully autonomous."),
            ("sequential_testing", run_sequential_testing,
             "mSPRT always-valid p-values at 25/50/75/100% checkpoints. Charts + PDF."),
        ]:
            _REGISTRY.pop(name, None)
            register_module(ModuleSpec(name, lambda state, llm=None, db=None, _fn=fn, **kw:
                _fn(llm=llm, db=db, **{k: v for k, v in kw.items() if k not in _STRIP_KEYS}), "phase_2", "monitoring", desc))
        logger.info("V3: Phase 2 modules re-registered")
    except ImportError as e:
        logger.debug("V3 Phase 2 import failed: %s", e)

    # ── Re-register Phase 3 ────────────────────────────────────────────────────
    try:
        from continum.experimentation.post_analysis.analysis import (
            run_experiment_analysis, run_causal_analysis,
            run_simpsons_paradox_detector, run_roi_tracker,
            run_learnings_repository, run_pre_post_analysis,
        )
        for name, fn, desc in [
            ("experiment_analysis",     run_experiment_analysis,
             "Full statistical readout + segments + Simpson's + synthesis. Charts + PDF."),
            ("causal_analysis",         run_causal_analysis,
             "7-method causal engine (DiD/ITS/PSM/SC/Mediation/RDD/Simpsons). Charts + PDF."),
            ("simpsons_paradox",        run_simpsons_paradox_detector,
             "Simpson's paradox scanner across all dimensions. PDF report."),
            ("roi_tracker",             run_roi_tracker,
             "OLS counterfactual ROI attribution. Trajectory chart + PDF."),
            ("learnings_repository",    run_learnings_repository,
             "Semantic search + synthesis over experiment learnings. PDF report."),
            ("pre_post_analysis",       run_pre_post_analysis,
             "Pre-post IOR comparison with confounding warnings. PDF."),
        ]:
            _REGISTRY.pop(name, None)
            register_module(ModuleSpec(name, lambda state, llm=None, db=None, _fn=fn, **kw:
                _fn(llm=llm, db=db, **{k: v for k, v in kw.items() if k not in _STRIP_KEYS}), "phase_3", "analysis", desc))
        logger.info("V3: Phase 3 modules re-registered")
    except ImportError as e:
        logger.debug("V3 Phase 3 import failed: %s", e)

    # ── Re-register Phase 4 ────────────────────────────────────────────────────
    try:
        from continum.experimentation.deployment import (
            run_uplift_modeller, run_decision_engine,
        )
        for name, fn, desc in [
            ("uplift_modeller",  run_uplift_modeller,
             "T-Learner uplift model + Qini curve + quartile breakdown. Charts + PDF + CSV."),
            ("decision_engine",  run_decision_engine,
             "Ship/no-ship recommendation with segment-level rollout plan. PDF report."),
        ]:
            _REGISTRY.pop(name, None)
            register_module(ModuleSpec(name, lambda state, llm=None, db=None, _fn=fn, **kw:
                _fn(llm=llm, db=db, **{k: v for k, v in kw.items() if k not in _STRIP_KEYS}), "phase_4", "deploy", desc))
        logger.info("V3: Phase 4 modules re-registered")
    except ImportError as e:
        logger.debug("V3 Phase 4 import failed: %s", e)

    # ── Analytical chain (multi-stage) ─────────────────────────────────────────
    try:
        from continum.insights.cognition import run_analytical_chain
        _REGISTRY.pop("analytical_chain", None)
        register_module(ModuleSpec(
            "analytical_chain",
            lambda state, llm=None, db=None, **kw: run_analytical_chain(
                experiment_name=kw.get("experiment_name", ""),
                db=db, llm=llm,
                bus=state if hasattr(state, "emit") else None,
                session_id=kw.get("session_id", "default"),
                depth=int(kw.get("depth", 3)),
            ),
            "intelligence", "chain",
            "Full multi-stage analytical chain: analysis → causal → ROI → uplift → decision.",
        ))
        logger.info("V3: analytical_chain registered")
    except ImportError as e:
        logger.debug("V3 analytical_chain import failed: %s", e)

    n = len([k for k in _REGISTRY if not k.startswith("_")])
    logger.info("V3 registry complete: %d total modules", n)
