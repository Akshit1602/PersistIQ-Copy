from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("continum.app.workflow")


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _banner(title: str) -> None:
    w = 78
    print(f"\n{'=' * w}\n  {title}\n{'=' * w}")


def _section(title: str) -> None:
    print(f"\n{'─' * 70}\n  {title}\n{'─' * 70}")


def _ok(msg: str)   -> None: print(f"  ✅  {msg}")
def _warn(msg: str) -> None: print(f"  ⚠️   {msg}")
def _err(msg: str)  -> None: print(f"  ❌  {msg}")


def _display_dataset_summary(datasets: dict) -> None:
    _banner("DATASET SUMMARY")
    for name, df in datasets.items():
        print(f"\n  {name.upper()}")
        print(f"    Rows   : {len(df):,}")
        print(f"    Columns: {len(df.columns)}")
        print(f"    Columns: {', '.join(df.columns[:12])}"
              + (" ..." if len(df.columns) > 12 else ""))


def _pick_experiment(db, override: Optional[str] = None) -> str:
    from continum.app.loader import list_experiments
    if override:
        return override
    exps = list_experiments(db)
    if exps.empty:
        raise RuntimeError("No experiments found in gold_experiment_analysis")
    print("\n  Available Experiments:\n")
    for i, row in exps.iterrows():
        print(f"  {i+1}. {row['experiment_name']}")
    choice = input("\n  Select experiment number: ").strip()
    idx = (int(choice) - 1) if choice.isdigit() else 0
    return exps.iloc[idx]["experiment_name"]


# ─────────────────────────────────────────────────────────────────────────────
# PHASE RUNNERS
# ─────────────────────────────────────────────────────────────────────────────

def _run_step_1_init(data_dir: str):
    import duckdb
    from continum.api.bootstrap import bootstrap_from_connection
    _banner("STEP 1 — INITIALIZING ANALYTICAL ENGINE")
    db = duckdb.connect(":memory:")
    state = bootstrap_from_connection(mode="duckdb", client_name="PersistIQ Demo", db=db)
    _ok("Framework bootstrap completed")
    return db, state


def _run_step_2_ingest(db, data_dir: str) -> dict:
    from continum.app.loader import load_csvs, register_bronze, build_silver_layer, build_gold_layer
    _banner("STEP 2 — INGESTING MULTI-TABLE EXPERIMENT DATA")
    datasets = load_csvs(data_dir)
    register_bronze(db, datasets)
    build_silver_layer(db)
    build_gold_layer(db)
    _ok("Bronze / Silver / Gold medallion layers created")
    _display_dataset_summary(datasets)
    return datasets


def _run_step_3_select(db, override: Optional[str] = None) -> str:
    _banner("STEP 3 — EXPERIMENT SELECTION")
    exp = _pick_experiment(db, override)
    print(f"\n  Selected Experiment: {exp}\n")
    return exp


def _run_step_4_gold_mart(db, exp_name: str) -> None:
    _banner("STEP 4 — GOLD EXPERIMENT MART")
    try:
        df = db.execute(f"""
            SELECT * FROM gold_experiment_analysis
            WHERE experiment_name = '{exp_name}'
            LIMIT 10
        """).df()
        print(df.to_string(index=False))
    except Exception as e:
        _err(f"Could not preview gold mart: {e}")


def _run_step_5_analysis(db, exp_name: str, state) -> dict:
    from continum.core.orchestration.dags.analysis_dag import run_experiment_analysis_pipeline
    _banner("STEP 5 — RUNNING EXPERIMENT ANALYSIS")
    print("  [INFO] Executing deterministic experimentation pipeline")

    result = run_experiment_analysis_pipeline(
        experiment_id=exp_name,
        experiment_name=exp_name,
        db=db, llm=None, save_result=True,
    )
    return result


def _run_step_6_results(result: dict) -> None:
    _banner("STEP 6 — RESULTS")
    r = result.get("result")
    if r is None:
        _err(f"Analysis failed: {result.get('error', 'unknown')}")
        return

    primary = result.get("primary_metric") or r.primary_delta

    _section("PRIMARY METRIC")
    print(f"  KPI               : {primary.metric_display_name}")
    print(f"  Control IOR       : {primary.rate_control:.4f}")
    print(f"  Treatment IOR     : {primary.rate_treatment:.4f}")
    print(f"  Absolute Lift     : {primary.delta_pp:+.2f}pp")
    print(f"  Relative Lift     : {primary.delta_rel:+.2%}")
    print(f"  p-value           : {primary.p_value:.6f}")
    print(f"  Significant       : {primary.is_significant}")
    print(f"  Direction         : {primary.direction}")
    print(f"  95% CI            : [{primary.ci_lo:.4f}, {primary.ci_hi:.4f}]")

    _section("SRM CHECK")
    if r.srm_detected:
        _warn(f"SRM DETECTED (p={r.srm_p_value:.4f}) — results should be interpreted with caution")
    else:
        _ok(f"No SRM detected (p={r.srm_p_value:.4f})")

    _section("SEGMENT FINDINGS")
    if r.slice_findings:
        print(f"  {len(r.slice_findings)} segment slices computed\n")
        top = sorted(r.slice_findings, key=lambda s: abs(s.delta.delta_pp), reverse=True)[:5]
        for s in top:
            pf = "  ⚠️ Simpson's paradox" if s.simpsons_paradox_flag else ""
            sig = "✅" if s.is_heterogeneous else "—"
            print(f"  {sig}  {s.dimension_name}={s.dimension_value:<16}  "
                  f"Δ={s.delta.delta_pp:+.4f}pp  p={s.delta.p_value:.4f}{pf}")
    else:
        print("  No segment findings (insufficient slice sizes)")

    _section("RECOMMENDATION")
    print(f"  Verdict         : {r.verdict.value}")
    print(f"  Recommendation  : {r.ship_recommendation.value.replace('_', ' ').upper()}")
    if r.ship_blockers:
        for b in r.ship_blockers:
            _warn(f"Blocker: {b}")

    if result.get("narrative"):
        _section("NARRATIVE")
        print(f"  {result['narrative'][:600]}")


def _run_step_7_report(result: dict, exp_name: str) -> None:
    _banner("STEP 7 — REPORT GENERATION")
    r = result.get("result")
    if r is None:
        _warn("Skipping report — no result available")
        return
    try:
        from continum.core.intelligence.narrative import generate_enhanced_report
        out = generate_enhanced_report(
            result=r,
            causal_estimates=result.get("causal_estimates", []),
            output_path=f"report_{exp_name[:30]}.pdf",
            llm=None,
        )
        _ok(f"Report saved → {out}")
    except Exception as e:
        _warn(f"Report generation skipped: {e}")


def _run_step_8_executive_summary(result: dict) -> None:
    from continum.core.intelligence.narrative import generate_decision_memo
    _banner("EXECUTIVE READOUT")
    r = result.get("result")
    if r is None:
        return
    memo = generate_decision_memo(r, llm=None)
    print(f"\n  {memo}\n")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN WORKFLOW
# ─────────────────────────────────────────────────────────────────────────────

def run_demo_workflow(
    data_dir: str = "./sample_data",
    experiment_name: Optional[str] = None,
) -> None:
    _banner("CONTINUM — EXPERIMENTATION INTELLIGENCE")

    try:
        db, state = _run_step_1_init(data_dir)
        datasets  = _run_step_2_ingest(db, data_dir)
        exp_name  = _run_step_3_select(db, experiment_name)
        _run_step_4_gold_mart(db, exp_name)
        result    = _run_step_5_analysis(db, exp_name, state)
        _run_step_6_results(result)
        _run_step_7_report(result, exp_name)
        _run_step_8_executive_summary(result)
    except KeyboardInterrupt:
        print("\n\n  Interrupted.")
    except Exception as e:
        _err(f"Workflow failed: {e}")
        import traceback
        traceback.print_exc()


__all__ = ["run_demo_workflow"]
