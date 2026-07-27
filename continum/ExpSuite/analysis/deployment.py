from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("continum.ExpSuite.analysis.deployment")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _build_uplift_features(df: pd.DataFrame) -> pd.DataFrame:
    feats = df.copy()
    feats["converted_to_order"] = pd.to_numeric(
        feats["converted_to_order"], errors="coerce"
    ).fillna(0)

    if "account_segment" in feats.columns:
        feats["seg_num"] = pd.Categorical(
            feats["account_segment"],
            categories=["Core", "Growth", "Enterprise", "Individuals"],
        ).codes

    if "platform" in feats.columns:
        feats["is_web"] = (feats["platform"] == "web").astype(int)

    if "order_value" in feats.columns:
        feats["order_value_norm"] = (
            pd.to_numeric(feats["order_value"], errors="coerce")
            .fillna(0)
            .clip(upper=feats["order_value"].quantile(0.99) if len(feats) > 0 else 1)
        )
        max_v = feats["order_value_norm"].max()
        if max_v > 0:
            feats["order_value_norm"] /= max_v

    return feats


def _train_t_learner(features: pd.DataFrame, control: str) -> Tuple[Any, Any, List[str]]:
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        raise ImportError("scikit-learn required for Uplift Modeller: pip install scikit-learn")

    feat_cols = [c for c in ["seg_num", "is_web", "order_value_norm"] if c in features.columns]
    if not feat_cols:
        raise ValueError("No feature columns available for uplift model.")

    ctrl_df = features[features["variant"] == control]
    treat_df = features[features["variant"] != control]

    if len(ctrl_df) < 30 or len(treat_df) < 30:
        raise ValueError(f"Insufficient data: ctrl={len(ctrl_df)}, treat={len(treat_df)}")

    scaler = StandardScaler()
    X_ctrl = scaler.fit_transform(ctrl_df[feat_cols].fillna(0))
    y_ctrl = ctrl_df["converted_to_order"].values
    X_treat = scaler.transform(treat_df[feat_cols].fillna(0))
    y_treat = treat_df["converted_to_order"].values

    m_ctrl = LogisticRegression(max_iter=500, random_state=42, C=1.0)
    m_ctrl.fit(X_ctrl, y_ctrl)

    m_trt = LogisticRegression(max_iter=500, random_state=42, C=1.0)
    m_trt.fit(X_treat, y_treat)

    return m_ctrl, m_trt, feat_cols


def _compute_uplift_scores(
    features: pd.DataFrame, m_ctrl, m_trt, feat_cols: List[str]
) -> pd.Series:
    try:
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        X = scaler.fit_transform(features[feat_cols].fillna(0))
        p_ctrl = m_ctrl.predict_proba(X)[:, 1]
        p_treat = m_trt.predict_proba(X)[:, 1]
        return pd.Series(p_treat - p_ctrl, index=features.index)
    except Exception as e:
        logger.warning("Could not compute uplift scores: %s — returning zeros", e)
        return pd.Series(0.0, index=features.index)


def _compute_qini(features: pd.DataFrame, uplift_scores: pd.Series, control: str) -> Dict:
    try:
        df = features.copy()
        df["uplift"] = uplift_scores.values
        df["is_treated"] = (df["variant"] != control).astype(int)
        df = df.sort_values("uplift", ascending=False).reset_index(drop=True)

        n = len(df)
        gains = []
        n_t, n_c, c_t, c_c = 0, 0, 0, 0
        for _, row in df.iterrows():
            if row["is_treated"] == 1:
                n_t += 1
                c_t += int(row["converted_to_order"])
            else:
                n_c += 1
                c_c += int(row["converted_to_order"])
            incr = (c_t / n_t if n_t > 0 else 0) - (c_c / n_c if n_c > 0 else 0)
            gains.append(incr)

        qini = float(np.trapz(gains) / n)
        if qini > 0.15:
            interp = "strong"
        elif qini > 0.05:
            interp = "moderate"
        elif qini > 0.0:
            interp = "weak"
        else:
            interp = "no signal"
        return {"qini": round(qini, 4), "interpretation": interp}
    except Exception as e:
        logger.debug("Qini computation failed: %s", e)
        return {"qini": 0.0, "interpretation": "unavailable"}


# ─────────────────────────────────────────────────────────────────────────────
# MODULE [15] — UPLIFT MODELLER
# ─────────────────────────────────────────────────────────────────────────────


def run_uplift_modeller(llm=None, db=None, **kwargs) -> Optional[Dict]:
    print()
    print("╔" + "═" * 70 + "╗")
    print("║" + "  UPLIFT MODELLER — Module 15".ljust(70) + "║")
    print("║" + "  Phase 4 · Deploy · Individual causal effect estimation".ljust(70) + "║")
    print("╚" + "═" * 70 + "╝")
    print()
    print("  Method: T-Learner — train separate control/treatment models,")
    print("  subtract predictions to get per-user uplift score.\n")

    if db is None:
        print("  ❌ No database connection.")
        return None

    # Load experiment list
    try:
        exps = db.execute("""
            SELECT DISTINCT experiment_name,
                   COUNT(*) AS n,
                   MIN(created_at)::DATE AS start_date
            FROM gold_experiment_analysis
            WHERE experiment_name IS NOT NULL
            GROUP BY experiment_name
            ORDER BY start_date DESC
        """).df()
    except Exception as e:
        print(f"  ❌ {e}")
        return None

    exp_name = kwargs.get("experiment_name")
    if not exp_name:
        print("  Concluded / available experiments:")
        for i, row in exps.iterrows():
            print(f"  [{i+1}] {row['experiment_name']}  ({row['n']:,} rows  {row['start_date']})")
        while True:
            raw = input(f"\n  ❓ Select experiment [1-{len(exps)}]: ").strip()
            try:
                idx = int(raw) - 1
                exp_name = exps.iloc[idx]["experiment_name"]
                break
            except (ValueError, IndexError):
                print("     ⚠️  Invalid choice")

    df = db.execute(f"""
        SELECT * FROM gold_experiment_analysis
        WHERE experiment_name = '{exp_name}'
    """).df()

    if len(df) < 100:
        print(f"  ⚠️  Only {len(df)} rows — uplift model may be unreliable.")

    variants = sorted(df["variant"].dropna().unique().tolist())
    control = next((v for v in variants if "control" in v.lower()), variants[0])
    treatments = [v for v in variants if v != control]  # noqa: F841

    print(f"\n  ✅ Experiment : {exp_name}")
    print(f"  Rows         : {len(df):,}")
    print(f"  Variants     : {variants}")

    # Build features and train
    print("\n  Building feature matrix...")
    features = _build_uplift_features(df)

    print("  Training T-Learner...")
    try:
        m_ctrl, m_trt, feat_cols = _train_t_learner(features, control)
    except (ImportError, ValueError) as e:
        print(f"  ❌ {e}")
        return None

    print(f"  Features used: {feat_cols}")

    # Uplift scores
    uplift_scores = _compute_uplift_scores(features, m_ctrl, m_trt, feat_cols)
    features["uplift_score"] = uplift_scores

    # Qini
    qini = _compute_qini(features, uplift_scores, control)
    print(f"\n  Qini coefficient : {qini['qini']:.4f} ({qini['interpretation']})")

    # Segment distribution
    print("\n  Uplift distribution by segment:")
    print(f"  {'Segment':<20} {'Mean':>10} {'p75':>8} {'p25':>8} {'% positive':>12}")
    print("  " + "─" * 60)

    seg_uplift = {}
    if "account_segment" in df.columns:
        for seg in sorted(df["account_segment"].dropna().unique()):
            mask = (df["account_segment"] == seg).values
            scores = uplift_scores[mask]
            mu = float(scores.mean())
            p75 = float(np.percentile(scores, 75))
            p25 = float(np.percentile(scores, 25))
            pct_p = float((scores > 0).mean() * 100)
            seg_uplift[seg] = {"mean": mu, "p75": p75, "p25": p25, "pct_positive": pct_p}
            icon = "📈" if mu > 0.005 else ("📉" if mu < -0.005 else "➡️ ")
            print(
                f"  {icon} {seg:<18} {mu*100:>+8.3f}pp  {p75*100:>+6.3f}pp  "
                f"{p25*100:>+6.3f}pp  {pct_p:>10.1f}%"
            )

    # Register scores in DB
    uplift_df = df[["user_id"]].copy()
    uplift_df["uplift_score"] = uplift_scores.values
    uplift_df["experiment_name"] = exp_name
    if "account_segment" in df.columns:
        uplift_df["account_segment"] = df["account_segment"].values

    db.register("uplift_scores", uplift_df)
    print(f"\n  ✅ Uplift scores registered as 'uplift_scores' ({len(uplift_df):,} rows)")
    print("     Run Module [16] (Decision Engine) to generate targeting plan.")

    # LLM synthesis
    if llm is not None and seg_uplift:
        seg_summary = "; ".join(
            f"{s}: mean={v['mean']*100:+.2f}pp ({v['pct_positive']:.0f}% positive)"
            for s, v in seg_uplift.items()
        )
        narrative = llm.ask(
            f"Uplift model for '{exp_name}': Qini={qini['qini']:.4f} ({qini['interpretation']}). "
            f"Segment uplift: {seg_summary}. "
            "In 3-4 sentences: (1) which users respond best, "
            "(2) whether Qini is trustworthy, (3) recommended targeting strategy."
        )
        print(f"\n  Analysis:\n  {narrative}")

    return {
        "experiment": exp_name,
        "qini": qini["qini"],
        "qini_grade": qini["interpretation"],
        "seg_uplift": seg_uplift,
        "uplift_df": uplift_df,
        "model_ctrl": m_ctrl,
        "model_trt": m_trt,
        "feat_cols": feat_cols,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MODULE [16] — DECISION ENGINE
# ─────────────────────────────────────────────────────────────────────────────


def run_decision_engine(llm=None, db=None, **kwargs) -> Optional[Dict]:
    print()
    print("╔" + "═" * 70 + "╗")
    print("║" + "  DECISION ENGINE — Module 16".ljust(70) + "║")
    print("║" + "  Phase 4 · Deploy · Budget-constrained targeting optimisation".ljust(70) + "║")
    print("╚" + "═" * 70 + "╝")
    print()
    print("  Answers: which users to target, at this budget, to maximise incremental GMV.\n")

    if db is None:
        print("  ❌ No database connection.")
        return None

    # Load uplift scores
    try:
        uplift_df = db.execute("SELECT * FROM uplift_scores").df()
        exp_name = uplift_df["experiment_name"].iloc[0] if len(uplift_df) else "unknown"
        print(f"  Loaded {len(uplift_df):,} uplift scores for: {exp_name}")
    except Exception:
        print("  ❌ No uplift scores found. Run Module [15] first.")
        return None

    # Budget parameters
    budget = kwargs.get("budget")
    if budget is None:
        while True:
            raw = input("  ❓ Total targeting budget ($ e.g. 50000): ").strip().replace(",", "")
            try:
                budget = float(raw)
                if budget > 0:
                    break
            except ValueError:
                pass
            print("     ⚠️  Enter a positive number")

    cost_per_contact = kwargs.get("cost_per_contact")
    if cost_per_contact is None:
        while True:
            raw = input("  ❓ Cost per contact ($ per user, e.g. 0.80): ").strip()
            try:
                cost_per_contact = float(raw)
                if cost_per_contact > 0:
                    break
            except ValueError:
                pass
            print("     ⚠️  Enter a positive number")

    max_contacts = int(budget / cost_per_contact)
    print(
        f"\n  Budget: ${budget:,.0f}  Cost/contact: ${cost_per_contact:.2f}  "
        f"Max contacts: {max_contacts:,}"
    )

    # AOV
    avg_aov = float(kwargs.get("avg_aov", 4000.0))
    try:
        avg_aov = float(db.execute("""
            SELECT AVG(order_value) FROM gold_experiment_analysis
            WHERE order_value > 0 AND converted_to_order = TRUE
        """).fetchone()[0] or avg_aov)
    except Exception:
        pass

    uplift_df["expected_incr_gmv"] = uplift_df["uplift_score"] * avg_aov

    # Greedy optimisation
    eligible = uplift_df[uplift_df["uplift_score"] > 0].copy()
    eligible = eligible.sort_values("expected_incr_gmv", ascending=False).reset_index(drop=True)
    harmed = uplift_df[uplift_df["uplift_score"] <= 0].copy()

    allocated = eligible.head(max_contacts).copy()
    total_contacts = len(allocated)
    total_cost = total_contacts * cost_per_contact
    projected_gmv = float(allocated["expected_incr_gmv"].sum())
    roi = projected_gmv / total_cost if total_cost > 0 else 0

    # Print summary
    print()
    print("  ── Targeting Allocation ──────────────────────────────────────────────")
    print(f"  {'Group':<30} {'Users':>8} {'Avg uplift':>12} {'Proj. GMV':>14}")
    print("  " + "─" * 70)

    seg_alloc = {}
    if "account_segment" in allocated.columns:
        for seg in sorted(allocated["account_segment"].dropna().unique()):
            sr = allocated[allocated["account_segment"] == seg]
            s_gmv = float(sr["expected_incr_gmv"].sum())
            s_uplift = float(sr["uplift_score"].mean())
            seg_alloc[seg] = {"n": len(sr), "avg_uplift": s_uplift, "projected_gmv": s_gmv}
            print(
                f"  🎯 TREAT  {seg:<24} {len(sr):>8,} {s_uplift*100:>+10.3f}pp  "
                f"${s_gmv:>12,.0f}"
            )
        if "account_segment" in harmed.columns:
            for seg in sorted(harmed["account_segment"].dropna().unique()):
                n_h = (harmed["account_segment"] == seg).sum()
                if n_h > 0:
                    print(f"  🚫 HOLD   {seg:<24} {n_h:>8,} {'(negative uplift)':>26}")
    else:
        print(
            f"  🎯 TREAT  {'(all eligible)':<24} {total_contacts:>8,} "
            f"{float(allocated['uplift_score'].mean())*100:>+10.3f}pp  "
            f"${projected_gmv:>12,.0f}"
        )

    print("  " + "─" * 70)
    print(f"  {'TOTAL':<30} {total_contacts:>8,} {'':>12} ${projected_gmv:>12,.0f}")
    print(f"\n  Budget used     : ${total_cost:>10,.0f} of ${budget:,.0f}")
    print(f"  Projected ROI   : {roi:.1f}× (${projected_gmv:,.0f} GMV / ${total_cost:,.0f} spend)")
    print(f"  Users held back : {len(harmed):,} (negative expected uplift)")

    # Save targeting brief
    fname = f"targeting_brief_{exp_name[:30]}.csv"
    out_cols = ["user_id", "uplift_score", "expected_incr_gmv"] + (
        ["account_segment"] if "account_segment" in allocated.columns else []
    )
    allocated[out_cols].to_csv(fname, index=False)
    print(f"\n  📁 Targeting brief saved → {fname}")

    # LLM deployment plan
    if llm is not None:
        seg_summary = (
            "; ".join(
                f"{s}: {v['n']:,} users avg={v['avg_uplift']*100:+.2f}pp GMV=${v['projected_gmv']:,.0f}"
                for s, v in seg_alloc.items()
            )
            if seg_alloc
            else f"{total_contacts:,} users targeted"
        )

        plan = llm.ask(
            f"Deployment plan for '{exp_name}'. "
            f"Budget=${budget:,.0f}, cost/contact=${cost_per_contact:.2f}, "
            f"max={max_contacts:,}. Allocation: {seg_summary}. "
            f"Projected ROI: {roi:.1f}x. Users held back: {len(harmed):,}. "
            "Write exactly three sections: "
            "DEPLOYMENT PLAN (who to target, sequence, timeframe); "
            "IMPLICATIONS (what to monitor, success/failure signals); "
            "TRADE-OFFS (what we give up, conservative vs aggressive estimate, main risk). "
            "Plain business English, no emojis."
        )
        print(f"\n  Deployment Plan\n{'─'*68}")
        for line in plan.split("\n"):
            if line.strip():
                print(f"    {line}")

    return {
        "experiment": exp_name,
        "budget": budget,
        "cost_per_contact": cost_per_contact,
        "n_targeted": total_contacts,
        "projected_gmv": projected_gmv,
        "projected_roi": roi,
        "seg_allocation": seg_alloc,
        "n_held_back": len(harmed),
        "targeting_file": fname,
    }


__all__ = ["run_uplift_modeller", "run_decision_engine"]
