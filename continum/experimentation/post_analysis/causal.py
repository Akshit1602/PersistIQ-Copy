from __future__ import annotations

import logging
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger("continum.experimentation.post_analysis.causal")

CAUSAL_METHODS = {
    "1": ("DiD v2", "Difference-in-Differences with bootstrap CI + event study"),
    "2": ("ITS", "Interrupted Time Series — level + slope change"),
    "3": ("PSM", "Propensity Score Matching with balance diagnostics"),
    "4": ("Synthetic Ctrl", "Synthetic Control — SLSQP donor weighting + permutation test"),
    "5": ("Mediation", "Causal mediation — direct + indirect effect decomposition"),
    "6": ("RDD", "Regression Discontinuity — local-linear at threshold"),
    "7": ("Simpson's", "Simpson's paradox detector across all dimensions"),
    "8": ("All methods", "Run all applicable methods and synthesise"),
}


def _load_experiment_df(db, exp_name: str) -> Optional[pd.DataFrame]:
    if db is None:
        return None
    try:
        df = db.execute(f"""
            SELECT *
            FROM gold_experiment_analysis
            WHERE experiment_name = '{exp_name}'
        """).df()
        return df if len(df) > 0 else None
    except Exception as e:
        logger.warning("Could not load experiment data: %s", e)
        return None


def _load_timeseries(db) -> Optional[pd.Series]:
    if db is None:
        return None
    try:
        df = db.execute("""
            SELECT
                created_at::DATE AS date,
                AVG(CAST(converted_to_order AS DOUBLE)) AS ior
            FROM silver_inquiries
            GROUP BY 1 ORDER BY 1
        """).df()
        if df.empty:
            return None
        s = df.set_index(pd.to_datetime(df["date"]))["ior"].astype(float)
        return s
    except Exception as e:
        logger.debug("Time series load failed: %s", e)
        return None


def run_causal_analysis_full(
    db=None,
    llm=None,
    experiment_name: str = "",
    method: str = "",  # "did" | "its" | "psm" | "sc" | "mediation" | "rdd" | "simpsons" | "all"
    cutoff_date: str = "",
    pre_start: str = "",
    **kwargs,
) -> Dict:
    print("\n" + "=" * 72)
    print("  CAUSAL ANALYSIS ENGINE")
    print("  7-method causal inference for post-experiment analysis")
    print("=" * 72)

    # ── Load experiment data ───────────────────────────────────────────────
    if db is None:
        return {"error": "no_db"}

    if not experiment_name:
        try:
            rows = db.execute("""
                SELECT DISTINCT experiment_name, COUNT(*) AS n
                FROM gold_experiment_analysis
                GROUP BY 1 ORDER BY 2 DESC LIMIT 10
            """).fetchall()
            if not rows:
                return {"error": "No experiments found in gold layer"}
            print("\n  Available experiments:")
            for i, (name, n) in enumerate(rows, 1):
                print(f"    {i}. {name}  ({n:,} rows)")
            raw = input("\n  Select experiment number: ").strip()
            idx = (int(raw) - 1) if raw.isdigit() else 0
            experiment_name = rows[min(idx, len(rows) - 1)][0]
        except Exception as e:
            return {"error": str(e)}

    print(f"\n  Experiment: {experiment_name}")
    df = _load_experiment_df(db, experiment_name)
    if df is None or len(df) < 50:
        return {"error": f"Insufficient data for {experiment_name}"}

    # Detect variants
    control = "control"
    variants = [v for v in df.get("variant", pd.Series()).unique() if str(v) != "control"]
    treatment = variants[0] if variants else "treatment"

    # Detect dates
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"])
        auto_cutoff = str(df["created_at"].median().date())
        auto_pre = str(df["created_at"].min().date())
    else:
        auto_cutoff = cutoff_date or ""
        auto_pre = pre_start or ""

    cutoff = cutoff_date or auto_cutoff
    pre = pre_start or auto_pre

    # ── Method selection ───────────────────────────────────────────────────
    if not method:
        print("\n  Available methods:")
        for k, (name, desc) in CAUSAL_METHODS.items():
            print(f"    [{k}]  {name:<20} — {desc}")
        raw = input("\n  Choose method [1-8]: ").strip()
        method_map = {
            "1": "did",
            "2": "its",
            "3": "psm",
            "4": "sc",
            "5": "mediation",
            "6": "rdd",
            "7": "simpsons",
            "8": "all",
        }
        method = method_map.get(raw, "did")

    results: Dict = {"experiment": experiment_name, "method": method}

    # ── Run selected method ────────────────────────────────────────────────
    if method in ("did", "all"):
        try:
            from continum.experimentation.causal.engine import run_did_v2

            segments = (
                df["account_segment"].dropna().unique().tolist()
                if "account_segment" in df.columns
                else []
            )
            trt_units = [treatment] if not segments else segments[: len(segments) // 2]
            ctrl_units = [control] if not segments else segments[len(segments) // 2 :]
            did_result = run_did_v2(
                df=df,
                treatment_units=trt_units,
                control_units=ctrl_units,
                cutoff_date=cutoff,
                pre_start=pre,
                unit_col="variant" if not segments else "account_segment",
            )
            results["did"] = did_result
            _print_causal_result("DiD v2", did_result)
        except Exception as e:
            results["did"] = {"error": str(e)}
            logger.warning("DiD failed: %s", e)

    if method in ("its", "all"):
        try:
            from continum.experimentation.causal.engine import run_its_enhanced

            ts = _load_timeseries(db)
            if ts is not None and len(ts) > 20:
                its_result = run_its_enhanced(ts, cutoff_date=cutoff, pre_start=pre)
                results["its"] = its_result
                _print_causal_result("ITS", its_result)
            else:
                results["its"] = {"error": "Insufficient time series data"}
        except Exception as e:
            results["its"] = {"error": str(e)}

    if method in ("psm", "all"):
        try:
            from continum.experimentation.causal.balance import plot_love_plot
            from continum.experimentation.causal.engine import run_psm_full

            psm_result = run_psm_full(
                df=df,
                outcome_col="converted_to_order",
                treatment_col="variant",
                control_label="control",
            )
            results["psm"] = psm_result
            _print_causal_result("PSM", psm_result)

            # Love plot
            if "smd_after" in psm_result:
                bal = {r["covariate"]: r for r in psm_result["smd_after"]}
                bal_full = {
                    k: {
                        "covariate": k,
                        "smd": v["smd"],
                        "flag": v["smd"] > 0.10,
                        "mean_ctrl": 0,
                        "mean_trt": 0,
                    }
                    for k, v in bal.items()
                }
                plot_love_plot(bal_full, experiment_name)
                print("  📁 Love plot saved → love_plot.png")
        except Exception as e:
            results["psm"] = {"error": str(e)}

    if method in ("sc", "all"):
        try:
            from continum.experimentation.causal.engine import run_synthetic_control_v2

            if "account_segment" in df.columns:
                segs = df["account_segment"].dropna().unique().tolist()
                if len(segs) >= 3:
                    trt_seg = segs[0]
                    donors = segs[1:]
                    sc_result = run_synthetic_control_v2(
                        df=df,
                        treatment_unit=trt_seg,
                        donor_units=donors,
                        cutoff_date=cutoff,
                        pre_start=pre,
                    )
                    results["sc"] = sc_result
                    _print_causal_result("Synthetic Control", sc_result)
                else:
                    results["sc"] = {"error": "Need ≥3 segments for Synthetic Control"}
            else:
                results["sc"] = {"error": "account_segment column required"}
        except Exception as e:
            results["sc"] = {"error": str(e)}

    if method in ("mediation", "all"):
        try:
            from continum.experimentation.causal.engine import run_mediation_analysis

            med_col = next(
                (
                    c
                    for c in ["has_billing_profile", "is_active_30d", "platform"]
                    if c in df.columns
                ),
                None,
            )
            if med_col:
                med_result = run_mediation_analysis(
                    df=df,
                    treatment_col="variant",
                    mediator_col=med_col,
                    outcome_col="converted_to_order",
                )
                results["mediation"] = med_result
                _print_causal_result("Mediation", med_result)
            else:
                results["mediation"] = {"error": "No suitable mediator column found"}
        except Exception as e:
            results["mediation"] = {"error": str(e)}

    if method in ("rdd", "all"):
        try:
            from continum.experimentation.causal.engine import run_rdd_enhanced

            run_col = next(
                (
                    c
                    for c in ["propensity_score", "lifetime_orders", "personal_ior"]
                    if c in df.columns
                ),
                None,
            )
            if run_col:
                cutoff_val = float(df[run_col].dropna().median())
                rdd_result = run_rdd_enhanced(
                    df=df,
                    running_var=run_col,
                    cutoff=cutoff_val,
                )
                results["rdd"] = rdd_result
                _print_causal_result("RDD", rdd_result)
            else:
                results["rdd"] = {"error": "No continuous running variable found"}
        except Exception as e:
            results["rdd"] = {"error": str(e)}

    if method in ("simpsons", "all"):
        try:
            from continum.experimentation.causal.engine import detect_simpsons_paradox

            sp_result = detect_simpsons_paradox(df=df)
            results["simpsons"] = sp_result
            print(f"\n  {sp_result.get('verdict', '')}")
            if sp_result.get("paradoxes"):
                for p in sp_result["paradoxes"][:5]:
                    print(
                        f"    ⚠️  {p['dimension']}={p['level']}: "
                        f"segment Δ={p['segment_delta_pp']:+.2f}pp "
                        f"vs overall {p['overall_delta_pp']:+.2f}pp "
                        f"({p['pct_of_data']:.0%} of data)"
                    )
        except Exception as e:
            results["simpsons"] = {"error": str(e)}

    # ── Mine additional insights ───────────────────────────────────────────
    try:
        from continum.experimentation.analytical_reasoning import mine_additional_insights

        insights = mine_additional_insights(
            df=df,
            control=control,
            treatment=treatment,
        )
        results["additional_insights"] = insights
        if insights.get("time_decay"):
            print(f"\n  📊 Time decay: {insights['time_decay']['summary']}")
        if insights.get("cohort_effect"):
            print(f"  📊 Cohort effect: {insights['cohort_effect']['summary']}")
        if insights.get("cross_metric"):
            print(f"  📊 Cross-metric: {insights['cross_metric']['summary']}")
    except Exception as e:
        logger.debug("Insight mining failed: %s", e)

    # ── LLM causal narrative ───────────────────────────────────────────────
    if llm is not None:
        try:
            from continum.experimentation.analytical_reasoning import synthesise_findings

            ctx = {
                "experiment": experiment_name,
                "description": f"Causal analysis using {method}",
                "hypothesis": "(see experiment brief)",
                "team": "",
                "decision": "See statistical output",
                "reasoning": "",
                "overall_summary": str(
                    {
                        k: v.get("did_estimate_pp") or v.get("level_change_pp") or v.get("att_pp")
                        for k, v in results.items()
                        if isinstance(v, dict) and not v.get("error")
                    }
                )[:300],
                "segment_summary": "",
                "interesting_summary": "",
                "time_trend_summary": results.get("additional_insights", {})
                .get("time_decay", {})
                .get("summary", ""),
                "extra_insights": "",
                "past_learnings": "",
                "n_past_learnings": 0,
            }
            narrative = synthesise_findings(ctx, llm)
            results["narrative"] = narrative
            print("\n  ── Causal Analysis Narrative ──")
            for line in narrative.split("\n")[:20]:
                if line.strip():
                    print(f"    {line}")
        except Exception as e:
            logger.debug("Causal narrative failed: %s", e)

    # ── Publish to InsightBus ──────────────────────────────────────────────
    try:
        from continum.insights.insight_bus import get_bus

        bus = get_bus()
        for m_key, m_result in results.items():
            if isinstance(m_result, dict) and not m_result.get("error"):
                est = (
                    m_result.get("did_estimate_pp")
                    or m_result.get("level_change_pp")
                    or m_result.get("att_pp")
                    or m_result.get("avg_lift_pp")
                    or 0
                )
                bus.emit(
                    source="causal_analysis",
                    insight_type=__import__(
                        "continum.insights.insight_bus", fromlist=["InsightType"]
                    ).InsightType.CAUSAL,
                    severity=__import__(
                        "continum.insights.insight_bus", fromlist=["InsightSeverity"]
                    ).InsightSeverity.INFO,
                    message=f"Causal ({m_key}): estimate={est:+.3f}pp",
                    experiment_id=experiment_name,
                )
    except Exception:
        pass

    return results


def _print_causal_result(method_name: str, result: Dict) -> None:
    if result.get("error"):
        print(f"\n  ❌ {method_name}: {result['error']}")
        return
    print(f"\n  ── {method_name} ─────────────────────────────────────────────")
    keys_of_interest = [
        "did_estimate_pp",
        "level_change_pp",
        "att_pp",
        "avg_lift_pp",
        "discontinuity_pp",
        "indirect_effect_pp",
        "p_value",
        "is_significant",
        "parallel_trends_ok",
        "balance_ok",
        "fit_note",
        "balance_note",
        "parallel_trends_note",
        "verdict",
        "manipulation_note",
    ]
    for k in keys_of_interest:
        if k in result:
            val = result[k]
            if isinstance(val, float):
                print(f"    {k:<28}: {val:+.4f}")
            elif isinstance(val, bool):
                print(f"    {k:<28}: {'✅ Yes' if val else '❌ No'}")
            elif isinstance(val, str) and len(val) < 100:
                print(f"    {k:<28}: {val}")


__all__ = ["run_causal_analysis_full"]
