from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger("continum.analytics.roi")


# ─────────────────────────────────────────────────────────────────────────────
# OLS COUNTERFACTUAL
# ─────────────────────────────────────────────────────────────────────────────

def _ols_counterfactual(
    pre_series:  pd.Series,
    post_series: pd.Series,
) -> Dict:
    n_pre  = len(pre_series)
    n_post = len(post_series)
    if n_pre < 5 or n_post < 1:
        return {}

    x_pre  = np.arange(n_pre).reshape(-1, 1)
    y_pre  = pre_series.values.astype(float)
    x_post = np.arange(n_pre, n_pre + n_post).reshape(-1, 1)
    y_post = post_series.values.astype(float)

    try:
        import statsmodels.api as sm
        X_pre = sm.add_constant(x_pre)
        model = sm.OLS(y_pre, X_pre).fit()
        X_post = sm.add_constant(x_post)
        pred  = model.predict(X_post)
        se_fc = np.sqrt(model.mse_resid)
    except ImportError:
        # Fallback: numpy polyfit
        coeffs = np.polyfit(x_pre.ravel(), y_pre, 1)
        pred   = np.polyval(coeffs, x_post.ravel())
        se_fc  = float(np.std(y_pre - np.polyval(coeffs, x_pre.ravel())))

    effect     = y_post - pred
    cumulative = float(np.sum(effect))

    t_stat, p_val = stats.ttest_1samp(effect, 0.0)

    return {
        "predicted":         pred.tolist(),
        "actual":            y_post.tolist(),
        "point_effect":      effect.tolist(),
        "cumulative_effect": round(cumulative, 4),
        "mean_effect":       round(float(np.mean(effect)), 4),
        "p_value":           round(float(p_val), 6),
        "is_significant":    bool(p_val < 0.05),
        "se_forecast":       round(float(se_fc), 4),
        "n_pre":             n_pre,
        "n_post":            n_post,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROI SYNTHESIS CORE
# ─────────────────────────────────────────────────────────────────────────────

def run_roi_synthesis(
    df:               pd.DataFrame,
    ship_date:        str,
    experiment_name:  str          = "unknown",
    delta_ior:        float        = None,   # from experiment result; auto-computed if None
    delta_ci_lo:      float        = None,
    delta_ci_hi:      float        = None,
    aov:              float        = None,   # if None, computed from data
    gross_margin:     float        = 0.30,
    horizon_months:   int          = 12,
) -> Dict:
    if "created_at" not in df.columns:
        return {"error": "created_at column missing"}
    if "converted_to_order" not in df.columns:
        return {"error": "converted_to_order column missing"}

    df = df.copy()
    df["created_at"] = pd.to_datetime(df["created_at"])
    cut = pd.Timestamp(ship_date)

    pre  = df[df["created_at"] <  cut].copy()
    post = df[df["created_at"] >= cut].copy()

    if len(pre) < 10 or len(post) < 5:
        return {"error": f"Insufficient data: {len(pre)} pre / {len(post)} post rows"}

    # ── Daily IOR time series ─────────────────────────────────────────────
    def _daily_ior(frame: pd.DataFrame) -> pd.Series:
        return (
            frame.groupby(frame["created_at"].dt.date)["converted_to_order"]
            .mean()
            .rename("ior")
        )

    pre_ior  = _daily_ior(pre)
    post_ior = _daily_ior(post)

    # ── OLS counterfactual ────────────────────────────────────────────────
    ols = _ols_counterfactual(pre_ior, post_ior)

    # ── Observed metrics ──────────────────────────────────────────────────
    pre_ior_mean  = float(pre["converted_to_order"].mean())
    post_ior_mean = float(post["converted_to_order"].mean())

    # If delta_ior not supplied, derive from OLS
    if delta_ior is None:
        delta_ior = float(ols.get("mean_effect", post_ior_mean - pre_ior_mean))

    # AOV
    if aov is None:
        ov_col = next((c for c in ["order_value", "aov", "order_total"] if c in df.columns), None)
        if ov_col:
            aov = float(df.loc[df["converted_to_order"] == 1, ov_col].median() or 0)
        if not aov or aov <= 0:
            aov = 4000.0

    # Monthly volume
    n_days_pre  = max((pre["created_at"].max() - pre["created_at"].min()).days, 1)
    monthly_inq = len(pre) / n_days_pre * 30

    # ── DiD-based projection ──────────────────────────────────────────────
    inc_orders_mo  = monthly_inq * delta_ior
    inc_gmv_mo     = inc_orders_mo * aov
    inc_margin_mo  = inc_gmv_mo * gross_margin

    months = list(range(1, horizon_months + 1))
    cum_gmv    = [inc_gmv_mo * m    for m in months]
    cum_margin = [inc_margin_mo * m for m in months]

    if delta_ci_lo is not None and delta_ci_hi is not None:
        cum_gmv_lo = [monthly_inq * delta_ci_lo * aov * m for m in months]
        cum_gmv_hi = [monthly_inq * delta_ci_hi * aov * m for m in months]
    else:
        u = 0.25
        cum_gmv_lo = [v * (1 - u) for v in cum_gmv]
        cum_gmv_hi = [v * (1 + u) for v in cum_gmv]

    # ── Observed post-ship GMV (actual) ───────────────────────────────────
    ov_col = next((c for c in ["order_value", "aov", "order_total"] if c in df.columns), None)
    if ov_col:
        actual_post_gmv = float(post.loc[post["converted_to_order"] == 1, ov_col].sum())
        actual_pre_gmv  = float(pre.loc[pre["converted_to_order"]  == 1, ov_col].sum())
        days_post       = max((post["created_at"].max() - post["created_at"].min()).days, 1)
        days_pre        = max(n_days_pre, 1)
        annualised_inc  = (actual_post_gmv / days_post - actual_pre_gmv / days_pre) * 365
    else:
        actual_post_gmv = None
        actual_pre_gmv  = None
        annualised_inc  = None

    return {
        "experiment_name":   experiment_name,
        "ship_date":         ship_date,
        "pre_ior":           round(pre_ior_mean, 4),
        "post_ior":          round(post_ior_mean, 4),
        "delta_ior":         round(delta_ior, 4),
        "aov":               round(aov, 2),
        "monthly_inquiries": round(monthly_inq, 0),
        "gross_margin":      gross_margin,

        # Monthly projections
        "inc_orders_monthly":   round(inc_orders_mo, 1),
        "inc_gmv_monthly":      round(inc_gmv_mo, 2),
        "inc_margin_monthly":   round(inc_margin_mo, 2),
        "cumulative_gmv":       [round(v, 2) for v in cum_gmv],
        "cumulative_gmv_lo":    [round(v, 2) for v in cum_gmv_lo],
        "cumulative_gmv_hi":    [round(v, 2) for v in cum_gmv_hi],
        "cumulative_margin":    [round(v, 2) for v in cum_margin],
        "months":               months,
        "12m_gmv_central":      round(cum_gmv[-1], 2),
        "12m_margin_central":   round(cum_margin[-1], 2),

        # OLS counterfactual
        "ols_counterfactual":   ols,

        # Actuals
        "actual_post_gmv":      actual_post_gmv,
        "actual_pre_gmv":       actual_pre_gmv,
        "annualised_incremental_gmv": annualised_inc,
    }


__all__ = ["run_roi_synthesis"]
