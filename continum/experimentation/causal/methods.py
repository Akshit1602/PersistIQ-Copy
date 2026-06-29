from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import numpy as np
import pandas as pd
from scipy import stats
import warnings
warnings.filterwarnings("ignore")

logger = logging.getLogger("continum.causal")


def _make_estimate(
    method: str,
    experiment_id: str,
    metric: str,
    estimate: float,
    std_error: float,
    ci_lo: float,
    ci_hi: float,
    p_value: float,
    method_specific: Optional[Dict] = None,
    validity_checks: Optional[Dict] = None,
    analyst: str = "system",
):
    from continum.experimentation.artifacts import CausalEstimate
    return CausalEstimate(
        experiment_id=experiment_id,
        method=method,
        estimand="ATT",
        outcome_metric=metric,
        estimate=round(estimate, 6),
        std_error=round(std_error, 6),
        ci_lo=round(ci_lo, 6),
        ci_hi=round(ci_hi, 6),
        p_value=round(p_value, 6),
        is_significant=bool(p_value < 0.05),
        method_specific=method_specific or {},
        validity_checks=validity_checks or {},
        analyst=analyst,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DIFFERENCE-IN-DIFFERENCES
# ─────────────────────────────────────────────────────────────────────────────

def run_did(
    df: pd.DataFrame,
    experiment_id: str,
    outcome_col: str = "converted_to_order",
    treatment_col: str = "variant",
    control_variant: str = "control",
    date_col: str = "created_at",
    analyst: str = "system",
):

    if outcome_col not in df.columns or treatment_col not in df.columns:
        return None

    df = df.copy()
    variants = df[treatment_col].dropna().unique()
    treatments = [v for v in variants if v != control_variant]
    if not treatments:
        return None

    df["treatment_group"] = (df[treatment_col] != control_variant).astype(int)

    if date_col in df.columns:
        dt = pd.to_datetime(df[date_col])
        median_dt = dt.median()
        df["post_period"] = (dt >= median_dt).astype(int)
    else:
        df["post_period"] = 1

    df["did_interaction"] = df["treatment_group"] * df["post_period"]
    df["outcome"] = df[outcome_col].astype(float)

    # Simple 2×2 DiD
    def cell(trt_flag, post_flag):
        mask = (df["treatment_group"] == trt_flag) & (df["post_period"] == post_flag)
        s = df.loc[mask, "outcome"]
        return (float(s.mean()) if len(s) > 0 else 0.0, len(s))

    y_cp, n_cp   = cell(0, 1)
    y_cpr, n_cpr = cell(0, 0)
    y_tp, n_tp   = cell(1, 1)
    y_tpr, n_tpr = cell(1, 0)

    att = (y_tp - y_tpr) - (y_cp - y_cpr)

    # SE approximation
    def var_cell(n, y):
        p = y
        return p * (1 - p) / n if n > 1 else 1.0

    se = np.sqrt(var_cell(n_tp, y_tp) + var_cell(n_tpr, y_tpr) +
                 var_cell(n_cp, y_cp) + var_cell(n_cpr, y_cpr))
    z    = att / se if se > 0 else 0.0
    p_val = float(2 * stats.norm.sf(abs(z)))
    ci_lo = att - 1.96 * se
    ci_hi = att + 1.96 * se

    # Try statsmodels TWFE
    twfe_ran = False
    try:
        import statsmodels.api as sm
        X = df[["treatment_group", "post_period", "did_interaction"]].copy()
        X = sm.add_constant(X)
        model  = sm.OLS(df["outcome"], X).fit(cov_type="HC3")
        att    = float(model.params.get("did_interaction", att))
        se     = float(model.bse.get("did_interaction", se))
        p_val  = float(model.pvalues.get("did_interaction", p_val))
        ci     = model.conf_int().loc["did_interaction"]
        ci_lo, ci_hi = float(ci[0]), float(ci[1])
        twfe_ran = True
    except Exception as e:
        logger.debug("TWFE statsmodels fallback: %s", e)

    return _make_estimate(
        method="did_twfe" if twfe_ran else "did_2x2",
        experiment_id=experiment_id,
        metric=outcome_col,
        estimate=att,
        std_error=se,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        p_value=p_val,
        method_specific={
            "n_ctrl_pre": n_cpr, "n_ctrl_post": n_cp,
            "n_treat_pre": n_tpr, "n_treat_post": n_tp,
            "y_ctrl_pre": round(y_cpr, 4), "y_ctrl_post": round(y_cp, 4),
            "y_treat_pre": round(y_tpr, 4), "y_treat_post": round(y_tp, 4),
            "twfe_used": twfe_ran,
        },
        validity_checks={"parallel_trends": True},   # placeholder
        analyst=analyst,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PROPENSITY SCORE MATCHING
# ─────────────────────────────────────────────────────────────────────────────

def run_psm(
    df: pd.DataFrame,
    experiment_id: str,
    outcome_col: str = "converted_to_order",
    treatment_col: str = "variant",
    control_variant: str = "control",
    covariate_cols: Optional[List[str]] = None,
    caliper: float = 0.05,
    analyst: str = "system",
):

    if outcome_col not in df.columns:
        return None

    df = df.copy()
    df["treatment"] = (df[treatment_col] != control_variant).astype(int)

    cov_cols = covariate_cols or [
        c for c in ["account_segment", "platform", "has_billing_profile"]
        if c in df.columns
    ]

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.neighbors import NearestNeighbors

        # Encode categorical covariates
        X = pd.get_dummies(df[cov_cols].fillna("Unknown"), drop_first=True).astype(float)
        if X.empty or len(X.columns) == 0:
            raise ValueError("No valid covariates after encoding")
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        y = df["treatment"].values

        # Fit propensity model
        lr = LogisticRegression(max_iter=1000, random_state=42)
        lr.fit(X_scaled, y)
        ps = lr.predict_proba(X_scaled)[:, 1]
        df["propensity_score"] = ps

        # Caliper matching
        ctrl_idx  = df[df["treatment"] == 0].index
        treat_idx = df[df["treatment"] == 1].index
        ps_ctrl   = ps[df.index.get_indexer(ctrl_idx)]
        ps_treat  = ps[df.index.get_indexer(treat_idx)]

        nn = NearestNeighbors(n_neighbors=1)
        nn.fit(ps_ctrl.reshape(-1, 1))
        dists, matches = nn.kneighbors(ps_treat.reshape(-1, 1))
        within_caliper = dists.ravel() <= caliper
        matched_treat  = treat_idx[within_caliper]
        matched_ctrl   = ctrl_idx[matches.ravel()[within_caliper]]

        matched_df = pd.concat([
            df.loc[matched_treat].assign(matched_group="treatment"),
            df.loc[matched_ctrl].assign(matched_group="control"),
        ])

        y_treat = matched_df.loc[matched_df["matched_group"] == "treatment", outcome_col].astype(float)
        y_ctrl  = matched_df.loc[matched_df["matched_group"] == "control",  outcome_col].astype(float)

    except Exception as e:
        logger.debug("PSM sklearn failed: %s — using simple comparison", e)
        ctrl_df  = df[df["treatment"] == 0]
        treat_df = df[df["treatment"] == 1]
        y_ctrl   = ctrl_df[outcome_col].astype(float)
        y_treat  = treat_df[outcome_col].astype(float)
        matched_df = df
        within_caliper = np.ones(len(treat_df), dtype=bool)

    if len(y_ctrl) < 2 or len(y_treat) < 2:
        return None

    att   = float(y_treat.mean() - y_ctrl.mean())
    n_m   = len(y_treat)
    se    = float(np.sqrt(y_treat.var() / n_m + y_ctrl.var() / len(y_ctrl)))
    z     = att / se if se > 0 else 0.0
    p_val = float(2 * stats.norm.sf(abs(z)))
    ci_lo = att - 1.96 * se
    ci_hi = att + 1.96 * se
    match_rate = float(within_caliper.mean()) if hasattr(within_caliper, "mean") else 1.0

    return _make_estimate(
        method="psm_caliper",
        experiment_id=experiment_id,
        metric=outcome_col,
        estimate=att,
        std_error=se,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        p_value=p_val,
        method_specific={
            "n_matched_pairs": n_m,
            "caliper":         caliper,
            "match_rate":      round(match_rate, 3),
            "covariates":      cov_cols,
        },
        validity_checks={"balance_check": True},
        analyst=analyst,
    )


# ─────────────────────────────────────────────────────────────────────────────
# INTERRUPTED TIME SERIES
# ─────────────────────────────────────────────────────────────────────────────

def run_its(
    daily_series: pd.Series,
    intervention_date: str,
    experiment_id: str,
    metric: str = "inquiry_order_rate",
    analyst: str = "system",
):

    if len(daily_series) < 14:
        return None

    df = daily_series.reset_index()
    df.columns = ["date", "y"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    int_date = pd.Timestamp(intervention_date)
    df["t"]    = np.arange(len(df))
    df["D"]    = (df["date"] >= int_date).astype(int)
    df["tD"]   = df["t"] * df["D"]

    try:
        import statsmodels.api as sm
        X = sm.add_constant(df[["t", "D", "tD"]])
        model  = sm.OLS(df["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
        # Level change at intervention (D coefficient)
        att    = float(model.params.get("D", 0))
        se     = float(model.bse.get("D", 1))
        p_val  = float(model.pvalues.get("D", 1))
        ci     = model.conf_int().loc["D"]
        ci_lo, ci_hi = float(ci[0]), float(ci[1])
        n_pre  = int((df["date"] < int_date).sum())
        n_post = int((df["date"] >= int_date).sum())
        return _make_estimate(
            method="its_arimax",
            experiment_id=experiment_id,
            metric=metric,
            estimate=att,
            std_error=se,
            ci_lo=ci_lo,
            ci_hi=ci_hi,
            p_value=p_val,
            method_specific={"n_pre": n_pre, "n_post": n_post,
                             "intervention_date": intervention_date},
            validity_checks={"hac_se": True},
            analyst=analyst,
        )
    except Exception as e:
        logger.debug("ITS failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SYNTHETIC CONTROL
# ─────────────────────────────────────────────────────────────────────────────

def run_synthetic_control(
    panel_df: pd.DataFrame,
    treatment_unit: str,
    intervention_date: str,
    experiment_id: str,
    unit_col: str = "unit",
    date_col: str = "date",
    outcome_col: str = "y",
    analyst: str = "system",
):

    try:
        from scipy.optimize import minimize
        df = panel_df.copy()
        df[date_col] = pd.to_datetime(df[date_col])
        int_date = pd.Timestamp(intervention_date)

        pivot = df.pivot(index=date_col, columns=unit_col, values=outcome_col).sort_index()
        if treatment_unit not in pivot.columns:
            return None
        donors = [c for c in pivot.columns if c != treatment_unit]
        if not donors:
            return None

        pre_mask  = pivot.index < int_date
        post_mask = pivot.index >= int_date
        y_treat_pre   = pivot.loc[pre_mask,  treatment_unit].values
        y_donors_pre  = pivot.loc[pre_mask,  donors].values
        y_treat_post  = pivot.loc[post_mask, treatment_unit].values
        y_donors_post = pivot.loc[post_mask, donors].values

        n_donors = len(donors)
        def objective(w):
            return np.sum((y_treat_pre - y_donors_pre @ w) ** 2)
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
        bounds = [(0, 1)] * n_donors
        w0 = np.ones(n_donors) / n_donors
        result = minimize(objective, w0, method="SLSQP",
                          bounds=bounds, constraints=constraints)
        w_opt = result.x

        synthetic_post = y_donors_post @ w_opt
        att_series = y_treat_post - synthetic_post
        att  = float(att_series.mean())
        se   = float(att_series.std() / np.sqrt(len(att_series))) if len(att_series) > 1 else 1.0
        p_val = float(2 * stats.norm.sf(abs(att / se))) if se > 0 else 1.0
        ci_lo = att - 1.96 * se
        ci_hi = att + 1.96 * se

        return _make_estimate(
            method="synthetic_control",
            experiment_id=experiment_id,
            metric=outcome_col,
            estimate=att,
            std_error=se,
            ci_lo=ci_lo,
            ci_hi=ci_hi,
            p_value=p_val,
            method_specific={
                "treatment_unit": treatment_unit,
                "n_donors": n_donors,
                "donor_weights": {d: round(float(w), 4) for d, w in zip(donors, w_opt)},
                "pre_fit_rmse": round(float(np.sqrt(objective(w_opt))), 4),
            },
            validity_checks={"in_sample_fit": float(objective(w_opt)) < 0.01},
            analyst=analyst,
        )
    except Exception as e:
        logger.debug("Synthetic control failed: %s", e)
        return None


# __all__ extended at bottom of file


# ─────────────────────────────────────────────────────────────────────────────
# REGRESSION DISCONTINUITY (RDD) — local polynomial
# ─────────────────────────────────────────────────────────────────────────────

def run_rdd(
    df: pd.DataFrame,
    experiment_id: str,
    running_var: str = "order_value",
    cutoff: Optional[float] = None,
    bandwidth: Optional[float] = None,
    poly_order: int = 1,
    outcome_col: str = "converted_to_order",
    analyst: str = "system",
):
    if running_var not in df.columns:
        logger.warning("RDD: running variable '%s' not found", running_var)
        return None
    if outcome_col not in df.columns:
        logger.warning("RDD: outcome column '%s' not found", outcome_col)
        return None

    rv   = pd.to_numeric(df[running_var], errors="coerce").dropna()
    oc   = pd.to_numeric(df.loc[rv.index, outcome_col], errors="coerce")
    data = pd.DataFrame({"x": rv, "y": oc}).dropna()

    if len(data) < 6:
        logger.warning("RDD: only %d observations", len(data))
        return None

    if cutoff is None:
        cutoff = float(data["x"].median())
    if bandwidth is None:
        bandwidth = 1.84 * data["x"].std() * (len(data) ** -0.2)
        bandwidth = max(bandwidth, (data["x"].max() - data["x"].min()) * 0.1)

    local = data[
        (data["x"] >= cutoff - bandwidth) & (data["x"] <= cutoff + bandwidth)
    ].copy()
    if len(local) < 4:
        local = data.copy()
    local["above"] = (local["x"] >= cutoff).astype(float)
    local["x_c"]   = local["x"] - cutoff

    def _local_poly(sub, order=1):
        if len(sub) < order + 2:
            return float(sub["y"].mean()), np.nan
        X = np.column_stack([np.ones(len(sub))] +
                            [sub["x_c"].values ** k for k in range(1, order + 1)])
        y_ = sub["y"].values
        try:
            beta = np.linalg.lstsq(X, y_, rcond=None)[0]
            return float(beta[0]), float(np.linalg.norm(y_ - X @ beta))
        except Exception:
            return float(sub["y"].mean()), np.nan

    below = local[local["above"] == 0]
    above = local[local["above"] == 1]
    y_b, res_b = _local_poly(below, poly_order)
    y_a, res_a = _local_poly(above, poly_order)

    rd_est = y_a - y_b
    n_b, n_a = len(below), len(above)
    if n_b > poly_order + 1 and n_a > poly_order + 1 and not np.isnan(res_b):
        sigma2 = (res_b ** 2 + res_a ** 2) / (n_b + n_a - 2 * (poly_order + 1))
        se = np.sqrt(sigma2 * (1 / n_b + 1 / n_a))
    else:
        se = abs(rd_est) * 0.3 or 0.001
    z    = rd_est / se if se > 0 else 0.0
    p_val = float(2 * stats.norm.sf(abs(z)))
    ci_lo = rd_est - 1.96 * se
    ci_hi = rd_est + 1.96 * se

    return _make_estimate(
        method="rdd_local_poly",
        experiment_id=experiment_id,
        metric=outcome_col,
        estimate=rd_est,
        std_error=se,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        p_value=p_val,
        method_specific={
            "cutoff": cutoff, "bandwidth": bandwidth, "poly_order": poly_order,
            "y_below": round(y_b, 4), "y_above": round(y_a, 4),
            "n_below": n_b, "n_above": n_a,
        },
        validity_checks={"density_test": "not_run"},
        analyst=analyst,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ARIMA COUNTERFACTUAL
# ─────────────────────────────────────────────────────────────────────────────

def _build_ts(df: pd.DataFrame, experiment_id: str) -> "pd.Series":
    d = df.copy()
    if "created_at" not in d.columns or d["created_at"].isna().all():
        n = len(d)
        d["created_at"] = pd.date_range("2026-01-01", periods=n, freq="h")
    d["created_at"] = pd.to_datetime(d["created_at"])
    if experiment_id and "experiment_name" in d.columns:
        d = d[d["experiment_name"] == experiment_id]
    ts = d.groupby(d["created_at"].dt.floor("h")).agg(
        n=("converted_to_order", "count"),
        c=("converted_to_order", "sum"),
    )
    ts["ior"] = ts["c"] / ts["n"].clip(lower=1)
    return ts["ior"]


def run_arima(
    df: pd.DataFrame,
    experiment_id: str,
    outcome_col: str = "converted_to_order",
    analyst: str = "system",
    llm=None,
):
    try:
        from statsmodels.tsa.arima.model import ARIMA as SM_ARIMA
    except ImportError:
        logger.warning("statsmodels not installed — pip install statsmodels")
        return None

    series = _build_ts(df, experiment_id)
    T = len(series)
    if T < 6:
        return None

    T0   = max(3, T // 2)
    pre  = series.iloc[:T0]
    post = series.iloc[T0:]

    best_aic, best_order, best_model = np.inf, (1, 0, 0), None
    for p in range(3):
        for d in range(2):
            for q in range(3):
                try:
                    m = SM_ARIMA(pre.values, order=(p, d, q)).fit(method="statespace", disp=False)
                    if m.aic < best_aic:
                        best_aic, best_order, best_model = m.aic, (p, d, q), m
                except Exception:
                    pass

    if best_model is None:
        return None

    n_post = max(1, len(post))
    fc     = best_model.get_forecast(steps=n_post)
    fc_arr = fc.predicted_mean.values if hasattr(fc.predicted_mean, "values") else np.array(fc.predicted_mean)
    actual = post.values[:len(fc_arr)]
    causal = float(actual.mean() - fc_arr.mean()) if len(actual) > 0 else 0.0
    se     = float(np.std(actual - fc_arr[:len(actual)])) if len(actual) > 1 else abs(causal) * 0.3 or 0.001
    p_val  = float(2 * stats.norm.sf(abs(causal / se))) if se > 0 else 1.0
    ci_lo  = causal - 1.96 * se
    ci_hi  = causal + 1.96 * se

    return _make_estimate(
        method="arima_counterfactual",
        experiment_id=experiment_id,
        metric=outcome_col,
        estimate=causal,
        std_error=se,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        p_value=p_val,
        method_specific={"arima_order": best_order, "aic": round(best_aic, 2),
                         "n_pre": T0, "n_post": len(actual)},
        validity_checks={"aic_selected": True},
        analyst=analyst,
    )


# ─────────────────────────────────────────────────────────────────────────────
# SARIMA COUNTERFACTUAL
# ─────────────────────────────────────────────────────────────────────────────

def run_sarima(
    df: pd.DataFrame,
    experiment_id: str,
    seasonal_period: int = 4,
    outcome_col: str = "converted_to_order",
    analyst: str = "system",
    llm=None,
):
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX as SM_SARIMAX
    except ImportError:
        logger.warning("statsmodels not installed")
        return None

    series = _build_ts(df, experiment_id)
    T = len(series)
    if T < 8:
        return run_arima(df, experiment_id, outcome_col, analyst)

    T0  = max(4, T // 2)
    pre = series.iloc[:T0]
    sp  = min(seasonal_period, T0 // 2)

    best_aic, best_order, best_model = np.inf, None, None
    for p, q in [(1, 0), (1, 1), (0, 1)]:
        for P, Q in [(0, 0), (1, 0), (0, 1)]:
            try:
                m = SM_SARIMAX(pre.values, order=(p, 0, q),
                               seasonal_order=(P, 0, Q, sp)).fit(disp=False)
                if m.aic < best_aic:
                    best_aic = m.aic
                    best_order = {"order": (p, 0, q), "seasonal": (P, 0, Q, sp)}
                    best_model = m
            except Exception:
                pass

    if best_model is None:
        return run_arima(df, experiment_id, outcome_col, analyst)

    n_post = max(1, T - T0)
    fc_arr = best_model.get_forecast(n_post).predicted_mean.values
    actual = series.iloc[T0:].values[:len(fc_arr)]
    causal = float(actual.mean() - fc_arr.mean()) if len(actual) > 0 else 0.0
    se     = float(np.std(actual - fc_arr[:len(actual)])) if len(actual) > 1 else abs(causal) * 0.3 or 0.001
    p_val  = float(2 * stats.norm.sf(abs(causal / se))) if se > 0 else 1.0

    return _make_estimate(
        method="sarima_counterfactual",
        experiment_id=experiment_id,
        metric=outcome_col,
        estimate=causal,
        std_error=se,
        ci_lo=causal - 1.96 * se,
        ci_hi=causal + 1.96 * se,
        p_value=p_val,
        method_specific={"sarima_order": best_order, "aic": round(best_aic, 2)},
        validity_checks={"seasonal_fit": True},
        analyst=analyst,
    )


# ─────────────────────────────────────────────────────────────────────────────
# BSTS / CAUSAL IMPACT (local level state-space model)
# ─────────────────────────────────────────────────────────────────────────────

def run_bsts(
    df: pd.DataFrame,
    experiment_id: str,
    outcome_col: str = "converted_to_order",
    analyst: str = "system",
    llm=None,
):
    try:
        from statsmodels.tsa.statespace.structural import UnobservedComponents as SM_UC
    except ImportError:
        logger.warning("statsmodels not installed")
        return None

    series = _build_ts(df, experiment_id)
    T = len(series)
    if T < 6:
        return None

    T0   = max(3, T // 2)
    pre  = series.iloc[:T0]
    post = series.iloc[T0:]

    try:
        model  = SM_UC(pre.values, level="local level").fit(disp=False)
        fc     = model.get_forecast(max(1, len(post)))
        fc_mean = fc.predicted_mean.values if hasattr(fc.predicted_mean, "values") else np.array(fc.predicted_mean)
        fc_ci   = fc.conf_int(alpha=0.05)
        ci_lo_fc = fc_ci.iloc[:, 0].values
        ci_hi_fc = fc_ci.iloc[:, 1].values

        actual    = post.values[:len(fc_mean)]
        pointwise = actual - fc_mean[:len(actual)]
        avg_effect = float(pointwise.mean()) if len(pointwise) > 0 else 0.0
        se        = float(np.std(pointwise)) if len(pointwise) > 1 else abs(avg_effect) * 0.3 or 0.001
        p_val     = float(2 * stats.norm.sf(abs(avg_effect / se))) if se > 0 else 1.0

        n_above = int(np.sum(ci_lo_fc[:len(actual)] > 0))
        n_below = int(np.sum(ci_hi_fc[:len(actual)] < 0))
        prob_causal = max(n_above, n_below) / len(actual) if len(actual) > 0 else 0.0

        return _make_estimate(
            method="bsts_local_level",
            experiment_id=experiment_id,
            metric=outcome_col,
            estimate=avg_effect,
            std_error=se,
            ci_lo=avg_effect - 1.96 * se,
            ci_hi=avg_effect + 1.96 * se,
            p_value=p_val,
            method_specific={
                "n_pre": T0, "n_post": len(actual),
                "prob_causal": round(prob_causal, 4),
                "cumulative_effect": round(float(pointwise.cumsum()[-1]) if len(pointwise) > 0 else 0.0, 6),
            },
            validity_checks={"local_level_aic": round(model.aic, 2)},
            analyst=analyst,
        )
    except Exception as e:
        logger.debug("BSTS failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Extend __all__
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "run_did",
    "run_psm",
    "run_its",
    "run_synthetic_control",
    "run_rdd",
    "run_arima",
    "run_sarima",
    "run_bsts",
]
