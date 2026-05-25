from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import chi2 as _chi2_dist

from continum.core.experimentation.statistics import (
    proportion_test, means_test, compute_sample_size, compute_msprt_statistic,
)

logger = logging.getLogger("continum.phase2")


# ─────────────────────────────────────────────────────────────────────────────
# MODULE [6] — EXPERIMENT HEALTH MONITOR
# ─────────────────────────────────────────────────────────────────────────────

def run_health_monitor(llm=None, db=None, experiment_registry: Optional[List[Dict]] = None,
                       **kwargs) -> Dict:
    print()
    print("╔" + "═" * 70 + "╗")
    print("║" + "  EXPERIMENT HEALTH MONITOR (Phase 2)".ljust(70) + "║")
    print("║" + "  SRM · Guardrails · Trajectory · ETA to significance".ljust(70) + "║")
    print("╚" + "═" * 70 + "╝")

    if db is None:
        print("  ❌ No database connection.")
        return {}

    # ── Load available experiments ────────────────────────────────────────────
    try:
        exp_df = db.execute("""
            SELECT DISTINCT experiment_name,
                   MIN(created_at)::DATE AS start_date,
                   MAX(created_at)::DATE AS end_date,
                   COUNT(*) AS n_rows
            FROM gold_experiment_analysis
            WHERE experiment_name IS NOT NULL
            GROUP BY experiment_name
            ORDER BY start_date DESC
        """).df()
    except Exception as e:
        print(f"  ❌ Could not load experiments: {e}")
        return {}

    if exp_df.empty:
        print("  ⚠️  No experiment data found.")
        return {}

    print("\n  Available experiments:")
    for i, row in exp_df.iterrows():
        print(f"  [{i+1}] {row['experiment_name']}  ({row['n_rows']:,} rows  "
              f"{row['start_date']} → {row['end_date']})")

    exp_name = kwargs.get("experiment_name")
    if not exp_name:
        while True:
            raw = input(f"\n  ❓ Select experiment [1-{len(exp_df)}]: ").strip()
            try:
                idx = int(raw) - 1
                if 0 <= idx < len(exp_df):
                    exp_name = exp_df.iloc[idx]["experiment_name"]
                    break
            except ValueError:
                pass
            print("     ⚠️  Invalid choice")

    # ── Load data ─────────────────────────────────────────────────────────────
    df = db.execute(f"""
        SELECT * FROM gold_experiment_analysis
        WHERE experiment_name = '{exp_name}'
    """).df()

    if df.empty:
        print(f"  ⚠️  No data for {exp_name}")
        return {}

    variants = sorted(df["variant"].dropna().unique().tolist())
    control  = next((v for v in variants if "control" in v.lower()), variants[0])
    treatments = [v for v in variants if v != control]

    start_date = pd.to_datetime(df["created_at"]).min().date()
    today      = pd.Timestamp.now().date()
    days_elapsed = (today - start_date).days

    print(f"\n  Experiment  : {exp_name}")
    print(f"  Variants    : {variants}")
    print(f"  Days elapsed: {days_elapsed}")
    print(f"  Total rows  : {len(df):,}")

    report = {
        "experiment": exp_name, "days_elapsed": days_elapsed,
        "variants": variants, "srm": {}, "primary": {}, "guardrails": [],
    }

    # ── [1] SRM Check ─────────────────────────────────────────────────────────
    print(f"\n  [1/4] Sample Ratio Mismatch")
    counts = df["variant"].value_counts()
    n_total = counts.sum()
    expected = n_total / len(variants)
    chi2_val = sum((counts.get(v, 0) - expected) ** 2 / expected for v in variants)
    p_srm = float(1 - _chi2_dist.cdf(chi2_val, df=len(variants) - 1))
    srm_detected = p_srm < 0.01

    for v in variants:
        n = counts.get(v, 0)
        print(f"     {v:<18}: {n:>7,} ({n / n_total * 100:.1f}%)")
    flag = "🚨 SRM DETECTED" if srm_detected else "✅ Clean"
    print(f"  χ²={chi2_val:.3f}  p={p_srm:.4f}  {flag}")
    report["srm"] = {"detected": srm_detected, "p_value": round(p_srm, 6),
                     "chi2": round(chi2_val, 4)}

    # ── [2] Primary Metric Trajectory ─────────────────────────────────────────
    print(f"\n  [2/4] Primary Metric — IOR Trajectory")
    ctrl_df = df[df["variant"] == control]
    n_c = len(ctrl_df)
    c_c = int(ctrl_df["converted_to_order"].sum())
    ior_c = c_c / n_c if n_c > 0 else 0
    print(f"  {control:<18}: IOR={ior_c*100:.3f}%  n={n_c:,}  conv={c_c:,}")

    primary_results = {}
    for trt in treatments:
        trt_df = df[df["variant"] == trt]
        n_t = len(trt_df)
        c_t = int(trt_df["converted_to_order"].sum())
        alpha_adj = 0.05 / max(1, len(treatments))
        pr = proportion_test(n_c, c_c, n_t, c_t, alpha_adj)
        primary_results[trt] = pr
        sig = f"✅ SIGNIFICANT (p={pr['p_value']:.4f})" if pr["is_significant"] \
            else f"⏳ not yet (p={pr['p_value']:.4f})"
        print(f"  {trt} vs {control}: Δ={pr['delta_pp']:+.4f}pp  "
              f"CI=[{pr['ci_lo_pp']:+.3f},{pr['ci_hi_pp']:+.3f}]  {sig}")
    report["primary"] = primary_results

    # ── [3] ETA to Significance ────────────────────────────────────────────────
    print(f"\n  [3/4] ETA to Significance")
    daily_rate = n_c / max(days_elapsed, 1)
    for trt in treatments:
        pr = primary_results[trt]
        obs_delta = abs(pr.get("rate_treatment", 0) - ior_c)
        if obs_delta < 0.0005:
            print(f"  {trt}: Effect < 0.05pp — cannot estimate ETA")
            continue
        ss_needed = compute_sample_size(ior_c, obs_delta, 0.05, 0.80, len(variants))
        needed = ss_needed["n_per_variant"]
        if n_c >= needed:
            print(f"  {trt}: ✅ Sufficient sample ({n_c:,} ≥ {needed:,})")
        else:
            extra_days = int(np.ceil((needed - n_c) / max(daily_rate, 1)))
            eta = (pd.Timestamp.now() + pd.Timedelta(days=extra_days)).strftime("%Y-%m-%d")
            print(f"  {trt}: Need {needed:,} per variant. At {daily_rate:.0f}/day "
                  f"→ {extra_days} more days (ETA: {eta})")

    # ── [4] Guardrail Checks ───────────────────────────────────────────────────
    print(f"\n  [4/4] Guardrail Metrics")
    guardrail_cols = [c for c in ["order_value", "fulfillment_days"] if c in df.columns]
    violations = []
    if not guardrail_cols:
        print("  No guardrail columns found (order_value, fulfillment_days).")
    for g_col in guardrail_cols:
        ctrl_vals = ctrl_df[g_col].dropna().values.astype(float)
        for trt in treatments:
            tr_vals = df[df["variant"] == trt][g_col].dropna().values.astype(float)
            if len(ctrl_vals) < 10 or len(tr_vals) < 10:
                continue
            mr = means_test(ctrl_vals, tr_vals, 0.05)
            pct_chg = mr.get("delta_rel", 0) * 100
            breached = mr.get("is_significant") and abs(pct_chg) > 5
            flag = "🚨 BREACH" if breached else "✅ OK"
            if breached:
                violations.append({"metric": g_col, "variant": trt, "pct_change": pct_chg})
            print(f"  {g_col} ({trt} vs {control}): Δ={pct_chg:+.1f}%  "
                  f"p={mr.get('p_value', 1):.4f}  {flag}")
    report["guardrails"] = violations

    if llm is not None:
        summary = {"experiment": exp_name, "days_elapsed": days_elapsed,
                   "srm_detected": srm_detected, "violations": violations,
                   "primary": {t: {"delta_pp": v["delta_pp"], "p_value": v["p_value"],
                                   "significant": v["is_significant"]}
                                for t, v in primary_results.items()}}
        narrative = llm.narrate(
            summary,
            "Experiment health check. Provide: (1) overall health, "
            "(2) whether to continue or stop, (3) immediate risks, (4) recommendation."
        )
        print(f"\n  HEALTH SUMMARY\n{'─'*68}")
        print(narrative)
        print("─" * 68)

    return report


# ─────────────────────────────────────────────────────────────────────────────
# MODULE [7] — SEQUENTIAL TESTING
# ─────────────────────────────────────────────────────────────────────────────

def run_sequential_testing(llm=None, db=None, **kwargs) -> Dict:
    print()
    print("╔" + "═" * 70 + "╗")
    print("║" + "  SEQUENTIAL TESTING — Always-Valid P-values (mSPRT)".ljust(70) + "║")
    print("║" + "  Safe to peek at any time — no false positive inflation".ljust(70) + "║")
    print("╚" + "═" * 70 + "╝")

    print("\n  mSPRT p-values are valid at ANY point in the experiment.")
    print("  Standard p-values are only valid at the planned end date.\n")

    if db is None:
        print("  ❌ No database connection.")
        return {}

    # Load experiment
    try:
        exp_list = db.execute("""
            SELECT DISTINCT experiment_name, COUNT(*) AS n
            FROM gold_experiment_analysis
            WHERE experiment_name IS NOT NULL
            GROUP BY experiment_name ORDER BY n DESC
        """).df()
    except Exception as e:
        print(f"  ❌ {e}")
        return {}

    exp_name = kwargs.get("experiment_name")
    if not exp_name:
        for i, row in exp_list.iterrows():
            print(f"  [{i+1}] {row['experiment_name']}  ({row['n']:,} rows)")
        while True:
            raw = input(f"\n  ❓ Select experiment [1-{len(exp_list)}]: ").strip()
            try:
                idx = int(raw) - 1
                exp_name = exp_list.iloc[idx]["experiment_name"]
                break
            except (ValueError, IndexError):
                pass

    df = db.execute(f"""
        SELECT * FROM gold_experiment_analysis
        WHERE experiment_name = '{exp_name}'
        ORDER BY created_at
    """).df()

    variants = sorted(df["variant"].dropna().unique().tolist())
    control  = next((v for v in variants if "control" in v.lower()), variants[0])
    alpha    = float(kwargs.get("alpha", 0.05))
    threshold = 1.0 / alpha

    ctrl_df = df[df["variant"] == control]
    n_c = len(ctrl_df)
    c_c = int(ctrl_df["converted_to_order"].sum())

    print(f"\n  Experiment  : {exp_name}")
    print(f"  Alpha       : {alpha}  (boundary = {threshold:.1f})")
    print(f"  Control     : {control}  n={n_c:,}  conv={c_c:,}")

    results = {}
    for trt in [v for v in variants if v != control]:
        trt_df = df[df["variant"] == trt]
        n_t = len(trt_df)
        c_t = int(trt_df["converted_to_order"].sum())
        m = compute_msprt_statistic(n_c, c_c, n_t, c_t)
        crossed = m["e_value"] >= threshold
        p_msprt = min(1.0, 1.0 / max(m["e_value"], 1e-10))

        p_c = c_c / n_c if n_c > 0 else 0
        p_t = c_t / n_t if n_t > 0 else 0
        delta_pp = (p_t - p_c) * 100

        status = "🛑 STOP — boundary crossed (sufficient evidence)" if crossed \
            else "⏳ Continue — boundary not yet crossed"
        print(f"\n  {trt} vs {control}:")
        print(f"    n={n_t:,}  conv={c_t:,}  IOR={p_t*100:.3f}%")
        print(f"    Δ={delta_pp:+.4f}pp")
        print(f"    E-value          : {m['e_value']:.4f}  (boundary={threshold:.1f})")
        print(f"    mSPRT p-value    : {p_msprt:.6f}")
        print(f"    Status           : {status}")
        results[trt] = {
            "e_value": m["e_value"], "p_value": round(p_msprt, 6),
            "boundary_crossed": crossed, "delta_pp": delta_pp,
            "n_control": n_c, "n_treatment": n_t,
        }

    return {"experiment": exp_name, "alpha": alpha, "threshold": threshold,
            "results": results}


__all__ = ["run_health_monitor", "run_sequential_testing"]
