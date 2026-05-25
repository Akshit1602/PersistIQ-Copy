from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

from continum.core.experimentation.statistics import proportion_test, means_test

logger = logging.getLogger("continum.phase3")


# ─────────────────────────────────────────────────────────────────────────────
# PAIRWISE COMPARISON (multi-arm / CMAB)
# ─────────────────────────────────────────────────────────────────────────────

def run_pairwise_comparisons(
    df: pd.DataFrame,
    variants: List[str],
    control: str,
    alpha: float = 0.05,
    bonferroni: bool = True,
) -> pd.DataFrame:
    treatments = [v for v in variants if v != control]
    pairs = [(control, t) for t in treatments]
    pairs += [(treatments[i], treatments[j])
              for i in range(len(treatments))
              for j in range(i + 1, len(treatments))]

    n_comp    = len(pairs)
    alpha_adj = alpha / n_comp if bonferroni and n_comp > 1 else alpha

    rows = []
    for var_a, var_b in pairs:
        ga = df[df["variant"] == var_a]
        gb = df[df["variant"] == var_b]
        if len(ga) < 30 or len(gb) < 30:
            continue
        n_a, c_a = len(ga), int(ga["converted_to_order"].sum())
        n_b, c_b = len(gb), int(gb["converted_to_order"].sum())
        pr = proportion_test(n_a, c_a, n_b, c_b, alpha_adj)
        mr = {}
        if "order_value" in df.columns:
            mr = means_test(ga["order_value"].values.astype(float),
                            gb["order_value"].values.astype(float), alpha_adj)
        rows.append({
            "comparison":   f"{var_a} vs {var_b}",
            "baseline":     var_a,
            "variant":      var_b,
            "is_primary":   var_a == control,
            "n_baseline":   n_a, "n_variant": n_b,
            "ior_baseline": pr["rate_control"],
            "ior_variant":  pr["rate_treatment"],
            "delta_pp":     pr["delta_pp"],
            "ci_lo_pp":     pr["ci_lo_pp"],
            "ci_hi_pp":     pr["ci_hi_pp"],
            "p_value":      pr["p_value"],
            "significant":  pr["is_significant"],
            "direction":    pr["direction"],
            "effect_h":     pr["effect_size_h"],
            "aov_baseline": mr.get("mean_control", 0),
            "aov_variant":  mr.get("mean_treatment", 0),
            "aov_delta":    mr.get("delta_abs", 0),
            "aov_p_value":  mr.get("p_value", 1.0),
            "aov_sig":      mr.get("is_significant", False),
            "alpha_used":   alpha_adj,
            "bonferroni":   bonferroni,
            "n_comparisons": n_comp,
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# SEGMENT SLICE ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def compute_segment_slices(
    df: pd.DataFrame,
    variants: List[str],
    control: str,
    dimensions: Optional[List[str]] = None,
    alpha: float = 0.05,
) -> List[Dict]:
    from continum.artifacts.types import SliceFinding, MetricDelta

    if dimensions is None:
        dimensions = [c for c in ["account_segment", "platform", "category", "country"]
                      if c in df.columns]

    treatments = [v for v in variants if v != control]
    if not treatments:
        return []
    treatment = treatments[0]

    overall_ctrl = df[df["variant"] == control]
    overall_trt  = df[df["variant"] == treatment]
    overall_pr = proportion_test(
        len(overall_ctrl), int(overall_ctrl["converted_to_order"].sum()),
        len(overall_trt),  int(overall_trt["converted_to_order"].sum()),
    )
    overall_delta = overall_pr["delta_pp"]

    slices = []
    for dim in dimensions:
        if dim not in df.columns:
            continue
        for level in df[dim].dropna().unique():
            sub = df[df[dim] == level]
            c_sub = sub[sub["variant"] == control]
            t_sub = sub[sub["variant"] == treatment]
            if len(c_sub) < 20 or len(t_sub) < 20:
                continue
            pr = proportion_test(
                len(c_sub), int(c_sub["converted_to_order"].sum()),
                len(t_sub), int(t_sub["converted_to_order"].sum()), alpha,
            )
            delta = MetricDelta(
                metric_name="inquiry_order_rate",
                metric_display_name="IOR",
                control_variant=control,
                treatment_variant=treatment,
                n_control=len(c_sub),
                n_treatment=len(t_sub),
                rate_control=pr["rate_control"],
                rate_treatment=pr["rate_treatment"],
                delta_pp=pr["delta_pp"],
                delta_abs=pr["delta_abs"],
                delta_rel=pr["delta_rel"],
                ci_lo=pr["ci_lo"],
                ci_hi=pr["ci_hi"],
                p_value=pr["p_value"],
                effect_size=pr["effect_size_h"],
                is_significant=pr["is_significant"],
                direction=pr["direction"],
                alpha=alpha,
            )
            # Simpson's paradox flag: slice effect contradicts overall
            simpsons_flag = (
                pr["delta_pp"] * overall_delta < 0  # opposite sign
                and abs(pr["delta_pp"]) > 0.001      # non-trivial
            )
            slices.append(SliceFinding(
                experiment_id=df["experiment_name"].iloc[0] if "experiment_name" in df.columns else "",
                metric_name="inquiry_order_rate",
                dimension_name=dim,
                dimension_value=str(level),
                n_slice=len(sub),
                delta=delta,
                is_heterogeneous=pr["is_significant"],
                simpsons_paradox_flag=simpsons_flag,
            ))
    return slices


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL ANALYSIS MENU
# ─────────────────────────────────────────────────────────────────────────────

def run_causal_analysis(llm=None, db=None, **kwargs) -> Any:
    print()
    print("╔" + "═" * 70 + "╗")
    print("║  CAUSAL ANALYSIS".ljust(71) + "║")
    print("║  Choose the right method for your situation".ljust(71) + "║")
    print("╚" + "═" * 70 + "╝")
    print("""
  AFTER RANDOMISED A/B
  [1]  A/B Test Analysis        — gold standard, variant assignment was random
  [2]  Pre-Post Analysis        — 100% rollout, compare before vs after

  WITHOUT FULL RANDOMISATION
  [3]  Diff-in-Differences      — partial rollout with control group
  [4]  Interrupted Time Series  — 100% rollout, long pre-period
  [5]  Propensity Score Match   — observational, self-selection
  [6]  Regression Discontinuity — treatment assigned at score threshold
  [7]  Synthetic Control        — one treated unit, donor pool
  [8]  ARIMA Counterfactual     — time-series counterfactual
  [9]  SARIMA                   — seasonal ARIMA
  [10] BSTS / Causal Impact     — state-space model
""")

    from continum.core.causal.methods import (
        run_did, run_psm, run_its, run_synthetic_control,
        run_rdd, run_arima, run_sarima, run_bsts,
    )

    choice = kwargs.get("method_choice")
    if not choice:
        while True:
            choice = input("  ❓ Choose method [1-10]: ").strip()
            if choice in [str(i) for i in range(1, 11)]:
                break
            print("     ⚠️  Enter 1-10")

    # Load experiment data
    df = kwargs.get("df")
    if df is None and db is not None:
        exp_name = kwargs.get("experiment_name")
        if not exp_name:
            try:
                experiments = db.execute("""
                    SELECT DISTINCT experiment_name
                    FROM gold_experiment_analysis
                """).df()["experiment_name"].tolist()
                print("\n  Experiments:", experiments[:5])
                exp_name = input("  ❓ Experiment name: ").strip()
            except Exception:
                pass
        if exp_name:
            try:
                df = db.execute(f"""
                    SELECT * FROM gold_experiment_analysis
                    WHERE experiment_name = '{exp_name}'
                """).df()
            except Exception as e:
                logger.warning("Could not load df: %s", e)

    if df is None:
        df = pd.DataFrame()
    exp_name = (df["experiment_name"].iloc[0]
                if "experiment_name" in df.columns and len(df) > 0
                else "unknown")

    if choice == "1":
        from continum.core.orchestration.dags.analysis_dag import run_primary_analysis_task
        variants = sorted(df["variant"].dropna().unique())
        control  = next((v for v in variants if "control" in v.lower()), variants[0] if variants else "control")
        return run_primary_analysis_task(df, exp_name, exp_name, control_variant=control)
    elif choice == "2":
        return run_pre_post_analysis(llm=llm, df=df, db=db, **kwargs)
    elif choice == "3":
        return run_did(df, exp_name) if len(df) > 0 else {}
    elif choice == "4":
        if db:
            try:
                daily = db.execute("""
                    SELECT created_at::DATE AS d, AVG(CAST(converted_to_order AS DOUBLE)) AS v
                    FROM gold_experiment_analysis
                    WHERE experiment_name IS NOT NULL
                    GROUP BY d ORDER BY d
                """).df()
                series = daily.set_index("d")["v"]
                cutoff = str(series.index[len(series) // 2])
                return run_its(series, cutoff, exp_name)
            except Exception as e:
                logger.warning("ITS failed: %s", e)
        return {}
    elif choice == "5":
        return run_psm(df, exp_name) if len(df) > 0 else {}
    elif choice == "6":
        return run_rdd(df, exp_name)
    elif choice == "7":
        return run_synthetic_control(df, exp_name=exp_name)
    elif choice == "8":
        return run_arima(df, exp_name, llm=llm)
    elif choice == "9":
        return run_sarima(df, exp_name, llm=llm)
    elif choice == "10":
        return run_bsts(df, exp_name, llm=llm)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# PRE-POST ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def run_pre_post_analysis(llm=None, df=None, db=None,
                          intervention_date: Optional[str] = None, **kwargs) -> Dict:
    print()
    print("╔" + "═" * 70 + "╗")
    print("║  PRE-POST ANALYSIS".ljust(71) + "║")
    print("║  ⚠️  Weak causal claim — confounded by seasonality & concurrent changes".ljust(71) + "║")
    print("╚" + "═" * 70 + "╝")
    print()

    if df is None and db is not None:
        try:
            df = db.execute("""
                SELECT * FROM gold_experiment_analysis
                ORDER BY created_at
            """).df()
        except Exception as e:
            print(f"  ❌ {e}"); return {}

    if df is None or len(df) == 0:
        print("  ❌ No data provided."); return {}

    df = df.copy()
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["converted_to_order"] = pd.to_numeric(df["converted_to_order"], errors="coerce").fillna(0)

    if intervention_date is None:
        min_d = df["created_at"].min().strftime("%Y-%m-%d")
        max_d = df["created_at"].max().strftime("%Y-%m-%d")
        print(f"  Date range: {min_d} → {max_d}")
        intervention_date = input("  ❓ Intervention / ship date (YYYY-MM-DD): ").strip()

    cutoff = pd.Timestamp(intervention_date)
    pre  = df[df["created_at"] < cutoff]
    post = df[df["created_at"] >= cutoff]

    if len(pre) < 30 or len(post) < 30:
        print(f"  ⚠️  Insufficient data: pre={len(pre)}, post={len(post)}")
        return {"error": "insufficient_data"}

    n_pre, c_pre   = len(pre), int(pre["converted_to_order"].sum())
    n_post, c_post = len(post), int(post["converted_to_order"].sum())
    ior_pre  = c_pre  / n_pre
    ior_post = c_post / n_post
    delta_pp = (ior_post - ior_pre) * 100

    pr = proportion_test(n_pre, c_pre, n_post, c_post)

    print(f"  Pre-period  : {n_pre:,} rows  IOR={ior_pre*100:.3f}%")
    print(f"  Post-period : {n_post:,} rows  IOR={ior_post*100:.3f}%")
    print(f"  Δ           : {delta_pp:+.4f}pp  p={pr['p_value']:.4f}  "
          f"{'SIGNIFICANT' if pr['is_significant'] else 'not significant'}")
    print()
    print("  ⚠️  CONFOUNDING WARNINGS:")
    print("     - Does not account for seasonality or weekday effects.")
    print("     - Concurrent changes during the post-period contaminate results.")
    print("     - Use DiD or ITS for stronger causal claims.")

    result = {
        "method": "pre_post",
        "intervention_date": intervention_date,
        "n_pre": n_pre, "n_post": n_post,
        "ior_pre": round(ior_pre, 6),
        "ior_post": round(ior_post, 6),
        "delta_pp": round(delta_pp, 4),
        "p_value": pr["p_value"],
        "is_significant": pr["is_significant"],
        "ci_lo_pp": pr["ci_lo_pp"],
        "ci_hi_pp": pr["ci_hi_pp"],
    }

    if llm is not None:
        narrative = llm.ask(
            f"Pre-post analysis: IOR {ior_pre*100:.3f}% → {ior_post*100:.3f}% "
            f"(Δ={delta_pp:+.4f}pp, p={pr['p_value']:.4f}). "
            "Interpret the result in 2 sentences, noting confounding risks."
        )
        print(f"\n  Interpretation: {narrative[:300]}")
        result["narrative"] = narrative

    return result


# ─────────────────────────────────────────────────────────────────────────────
# SIMPSON'S PARADOX DETECTOR
# ─────────────────────────────────────────────────────────────────────────────

def run_simpsons_paradox_detector(llm=None, db=None, **kwargs) -> Dict:
    print()
    print("╔" + "═" * 70 + "╗")
    print("║  SIMPSON'S PARADOX DETECTOR".ljust(71) + "║")
    print("╚" + "═" * 70 + "╝")

    df = kwargs.get("df")
    if df is None and db is not None:
        exp_name = kwargs.get("experiment_name")
        if not exp_name:
            try:
                exps = db.execute("""
                    SELECT DISTINCT experiment_name FROM gold_experiment_analysis
                """).df()["experiment_name"].tolist()
                print("\n  Experiments:")
                for i, e in enumerate(exps):
                    print(f"  [{i+1}] {e}")
                idx = int(input("  ❓ Select: ").strip()) - 1
                exp_name = exps[idx]
            except Exception as e:
                print(f"  ❌ {e}"); return {}
        try:
            df = db.execute(f"""
                SELECT * FROM gold_experiment_analysis
                WHERE experiment_name = '{exp_name}'
            """).df()
        except Exception as e:
            print(f"  ❌ {e}"); return {}

    if df is None or len(df) == 0:
        print("  ❌ No data."); return {}

    variants = sorted(df["variant"].dropna().unique())
    control  = next((v for v in variants if "control" in v.lower()), variants[0])
    treatments = [v for v in variants if v != control]
    ctrl_df = df[df["variant"] == control]
    dims = [c for c in ["account_segment", "platform", "category", "country"]
            if c in df.columns]

    results = {}
    for trt in treatments:
        trt_df = df[df["variant"] == trt]
        overall = proportion_test(
            len(ctrl_df), int(ctrl_df["converted_to_order"].sum()),
            len(trt_df),  int(trt_df["converted_to_order"].sum())
        )
        overall_delta = overall["delta_pp"]
        print(f"\n  Overall {trt} vs {control}: Δ={overall_delta:+.3f}pp  "
              f"p={overall['p_value']:.4f}")

        paradoxes = []
        for dim in dims:
            seg_deltas = []
            print(f"\n  Dimension: {dim}")
            for seg in df[dim].dropna().unique():
                c_s = ctrl_df[ctrl_df[dim] == seg]
                t_s = trt_df[trt_df[dim] == seg]
                if len(c_s) < 10 or len(t_s) < 10:
                    continue
                pr_s = proportion_test(
                    len(c_s), int(c_s["converted_to_order"].sum()),
                    len(t_s), int(t_s["converted_to_order"].sum())
                )
                seg_deltas.append(pr_s["delta_pp"])
                print(f"    {str(seg):<22} Δ={pr_s['delta_pp']:+.3f}pp  "
                      f"n={len(c_s)+len(t_s):,}")

            if seg_deltas:
                same_sign = all(d * overall_delta >= 0 for d in seg_deltas)
                if not same_sign:
                    paradoxes.append({
                        "dimension": dim,
                        "overall_delta": overall_delta,
                        "segment_deltas": seg_deltas,
                    })
                    print(f"  ⚠️  POSSIBLE SIMPSON'S PARADOX in {dim}: "
                          "segment effects contradict overall direction!")
                else:
                    print(f"  ✅ No paradox in {dim}")

        results[trt] = {
            "overall_delta": overall_delta,
            "paradoxes_detected": paradoxes,
            "n_paradoxes": len(paradoxes),
        }

    return results


# ─────────────────────────────────────────────────────────────────────────────
# ROI TRACKER
# ─────────────────────────────────────────────────────────────────────────────

def _fit_counterfactual_model(df_ts: pd.DataFrame, cutoff_date) -> Optional[Dict]:
    train = df_ts[df_ts["date"] < cutoff_date].copy().reset_index(drop=True)
    if len(train) < 30:
        return None

    n = len(train)
    X = np.zeros((n, 19))   # intercept + trend + 6 DOW + 11 month
    X[:, 0] = 1.0
    X[:, 1] = np.arange(n) / n
    dow = pd.to_datetime(train["date"]).dt.dayofweek
    month = pd.to_datetime(train["date"]).dt.month
    for d in range(1, 7):
        X[:, 1 + d] = (dow == d).astype(float)
    for m in range(1, 12):
        X[:, 7 + m] = (month == (m + 1)).astype(float)

    y = train["ior"].values
    try:
        coef = np.linalg.lstsq(X, y, rcond=None)[0]
    except Exception:
        return None

    y_hat  = X @ coef
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2     = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    mape   = np.mean(np.abs((y - y_hat) / np.clip(y, 0.01, 1))) * 100

    def forecast(dates):
        dates = pd.to_datetime(dates)
        n_p = len(dates)
        Xp  = np.zeros((n_p, 19))
        Xp[:, 0] = 1.0
        Xp[:, 1] = np.arange(n, n + n_p) / n
        d2 = dates.dt.dayofweek if hasattr(dates, "dt") else dates.dayofweek
        m2 = dates.dt.month if hasattr(dates, "dt") else dates.month
        for d in range(1, 7):
            Xp[:, 1 + d] = (d2 == d).astype(float)
        for m in range(1, 12):
            Xp[:, 7 + m] = (m2 == (m + 1)).astype(float)
        return np.clip(Xp @ coef, 0.01, 0.99)

    return {"r2": round(r2, 4), "mape": round(mape, 3), "n_train": n,
            "cutoff": cutoff_date, "forecast": forecast}


def run_roi_tracker(llm=None, db=None, **kwargs) -> Dict:
    print()
    print("╔" + "═" * 70 + "╗")
    print("║  ROI TRACKER — Post-Ship Counterfactual".ljust(71) + "║")
    print("╚" + "═" * 70 + "╝")

    if db is None:
        print("  ❌ No database connection."); return {}

    # Build daily IOR series from gold layer
    try:
        df_ts = db.execute("""
            SELECT
                created_at::DATE AS date,
                AVG(CAST(converted_to_order AS DOUBLE)) AS ior,
                COUNT(*) AS n_inquiries
            FROM gold_experiment_analysis
            WHERE converted_to_order IS NOT NULL
            GROUP BY created_at::DATE
            ORDER BY date
        """).df()
        df_ts["date"] = pd.to_datetime(df_ts["date"])
    except Exception as e:
        print(f"  ❌ Could not build daily series: {e}"); return {}

    if len(df_ts) < 30:
        print(f"  ⚠️  Only {len(df_ts)} days — need ≥ 30 for counterfactual modelling.")
        return {}

    cutoff = df_ts["date"].median()
    model  = _fit_counterfactual_model(df_ts, cutoff)
    if model is None:
        print("  ❌ Counterfactual model could not be fit."); return {}

    print(f"\n  Model fit R²            : {model['r2']:.4f}")
    print(f"  Pre-period MAPE         : {model['mape']:.2f}%")
    print(f"  Train period            : {len(df_ts[df_ts['date'] < cutoff])} days")

    # Forecast post-period
    post = df_ts[df_ts["date"] >= cutoff].copy()
    if len(post) == 0:
        print("  ⚠️  No post-period data.")
        return {}

    cf      = model["forecast"](post["date"])
    avg_aov = float(kwargs.get("avg_aov", 4000.0))
    try:
        avg_aov = float(db.execute("""
            SELECT AVG(order_value) FROM gold_experiment_analysis
            WHERE order_value > 0 AND converted_to_order = TRUE
        """).fetchone()[0] or avg_aov)
    except Exception:
        pass

    daily_inq = float(df_ts["n_inquiries"].mean())
    observed  = post["ior"].values[:len(cf)]
    lift      = observed - cf[:len(observed)]
    daily_gmv = lift * daily_inq * avg_aov
    total_gmv = float(daily_gmv.sum())

    print(f"  Avg daily IOR lift      : {np.mean(lift)*100:+.4f}pp")
    print(f"  Total GMV impact (post) : ${total_gmv:,.0f}")
    print(f"  Days with positive lift : {float(np.mean(lift > 0)*100):.1f}%")

    result = {
        "model_r2":          model["r2"],
        "avg_daily_lift_pp": float(np.mean(lift) * 100),
        "total_gmv":         round(total_gmv, 2),
        "pct_days_positive": float(np.mean(lift > 0) * 100),
    }

    if llm is not None:
        narrative = llm.ask(
            f"ROI counterfactual: avg_lift={result['avg_daily_lift_pp']:+.4f}pp, "
            f"total_GMV=${total_gmv:,.0f}. 2-sentence business interpretation."
        )
        print(f"\n  Interpretation: {narrative[:300]}")
        result["narrative"] = narrative

    return result


# ─────────────────────────────────────────────────────────────────────────────
# LEARNINGS REPOSITORY
# ─────────────────────────────────────────────────────────────────────────────

def run_learnings_repository(llm=None, db=None, **kwargs) -> Any:
    print()
    print("╔" + "═" * 70 + "╗")
    print("║  EXPERIMENT LEARNINGS REPOSITORY".ljust(71) + "║")
    print("║  Add · Search · Browse".ljust(71) + "║")
    print("╚" + "═" * 70 + "╝")
    print()
    print("  [1]  Search learnings")
    print("  [2]  Add new learning")
    print("  [3]  Browse all")

    action = kwargs.get("action")
    if not action:
        while True:
            action = input("\n  ❓ Choose [1/2/3]: ").strip()
            if action in ("1", "2", "3"):
                break

    if db is None:
        print("  ❌ No database connection."); return {}

    # Ensure learnings table exists
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS experiment_learnings (
                id VARCHAR,
                experiment_name VARCHAR,
                ship_decision VARCHAR,
                outcome TEXT,
                key_learning TEXT,
                what_worked TEXT,
                what_didnt TEXT,
                recommendation TEXT,
                follow_up_experiments TEXT,
                tags TEXT,
                recorded_at VARCHAR,
                recorded_by VARCHAR
            )
        """)
    except Exception:
        pass

    if action == "3":
        try:
            df = db.execute("""
                SELECT id, experiment_name, ship_decision, outcome, recorded_at
                FROM experiment_learnings ORDER BY recorded_at DESC
            """).df()
        except Exception as e:
            print(f"  ❌ {e}"); return {}
        print(f"\n  Repository: {len(df)} learning(s)\n")
        for _, row in df.iterrows():
            icon = {"ship": "✅", "no_ship": "❌", "partial_ship": "⚠️"}.get(
                row.get("ship_decision", ""), "⬜")
            print(f"  {icon} [{row['id']}] {row['experiment_name']}  ({row['recorded_at']})")
            print(f"       {str(row.get('outcome', ''))[:100]}\n")
        return df.to_dict("records")

    if action == "1":
        query = input("\n  ❓ Search query: ").strip()
        try:
            df = db.execute("SELECT * FROM experiment_learnings").df()
        except Exception as e:
            print(f"  ❌ {e}"); return {}
        if len(df) == 0:
            print("  No learnings yet."); return {}

        if llm is not None:
            all_text = "\n\n".join(
                f"[{r['id']}] {r['experiment_name']}: {r.get('key_learning', '')}. "
                f"Tags: {r.get('tags', '')}"
                for _, r in df.iterrows()
            )
            result = llm.ask(
                f'Search this learnings repository for: "{query}"\n\n{all_text}\n\n'
                "Return the 2-3 most relevant experiment IDs and a synthesis."
            )
            print(f"\n{result}")
            return result
        else:
            matches = df[df.apply(
                lambda r: query.lower() in str(r.values).lower(), axis=1)]
            print(f"\n  Found {len(matches)} match(es):")
            for _, row in matches.iterrows():
                print(f"  [{row['id']}] {row['experiment_name']}: {str(row.get('key_learning',''))[:80]}")
            return matches.to_dict("records")

    if action == "2":
        print("\n  Record a new experiment learning:\n")
        exp_name   = input("  ❓ Experiment name: ").strip()
        ship_raw   = input("  ❓ Ship decision [ship/no_ship/partial_ship]: ").strip()
        outcome    = input("  ❓ Outcome summary (1-2 sentences): ").strip()
        key_learn  = input("  ❓ Key learning: ").strip()
        worked     = input("  ❓ What worked: ").strip()
        didnt      = input("  ❓ What did NOT work: ").strip()
        recommend  = input("  ❓ Recommendation: ").strip()
        follow_ups = input("  ❓ Follow-up ideas (comma-sep): ").strip()
        tags       = input("  ❓ Tags (comma-sep): ").strip()

        try:
            count = db.execute("SELECT COUNT(*) FROM experiment_learnings").fetchone()[0]
        except Exception:
            count = 0
        new_id = f"L{count+1:03d}"

        db.execute("""
            INSERT INTO experiment_learnings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [new_id, exp_name, ship_raw, outcome, key_learn, worked, didnt,
              recommend, follow_ups, tags,
              pd.Timestamp.today().strftime("%Y-%m-%d"), "Analytics Team"])

        print(f"\n  ✅ Learning [{new_id}] recorded.")
        if llm is not None:
            synthesis = llm.narrate(
                {"id": new_id, "experiment": exp_name, "outcome": outcome,
                 "learning": key_learn},
                "A new experiment learning has been recorded. "
                "Distil the most important insight in 2 sentences."
            )
            print(f"\n  Insight: {synthesis}")
        return new_id

    return {}


__all__ = [
    "run_pairwise_comparisons",
    "compute_segment_slices",
    "run_causal_analysis",
    "run_pre_post_analysis",
    "run_simpsons_paradox_detector",
    "run_roi_tracker",
    "run_learnings_repository",
]
