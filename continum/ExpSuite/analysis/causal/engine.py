from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from scipy.stats import norm

logger = logging.getLogger("continum.causal.engine")

# ─────────────────────────────────────────────────────────────────────────────
# SHARED UTILITIES
# ─────────────────────────────────────────────────────────────────────────────


def _safe_ior(df: pd.DataFrame, col: str = "converted_to_order") -> float:
    if len(df) == 0 or col not in df.columns:
        return float("nan")
    return float(df[col].astype(float).mean())


def _proportion_se(p: float, n: int) -> float:
    return np.sqrt(p * (1 - p) / n) if n > 0 else np.nan


def _z_test(p1: float, n1: int, p2: float, n2: int, alpha: float = 0.05) -> Dict:
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2) if n1 > 0 and n2 > 0 else 1.0
    delta = p2 - p1
    z = delta / se if se > 0 else 0.0
    p_val = float(2 * norm.sf(abs(z)))
    z_crit = norm.ppf(1 - alpha / 2)
    return {
        "delta_pp": round(delta * 100, 4),
        "ci_lo_pp": round((delta - z_crit * se) * 100, 4),
        "ci_hi_pp": round((delta + z_crit * se) * 100, 4),
        "p_value": round(p_val, 6),
        "z_stat": round(z, 4),
        "is_significant": bool(p_val < alpha),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. DIFFERENCE-IN-DIFFERENCES v2
# ─────────────────────────────────────────────────────────────────────────────


def run_did_v2(
    df: pd.DataFrame,
    treatment_units: List,
    control_units: List,
    cutoff_date: str,
    pre_start: str,
    unit_col: str = "account_segment",
    outcome_col: str = "converted_to_order",
    date_col: str = "created_at",
    alpha: float = 0.05,
    n_bootstrap: int = 1_000,
    run_twfe: bool = True,
) -> Dict:
    cut = pd.Timestamp(cutoff_date)
    pre_s = pd.Timestamp(pre_start)

    data = df.copy()
    data[date_col] = pd.to_datetime(data[date_col])
    data = data[data[unit_col].isin(treatment_units + control_units)].copy()
    data = data[data[date_col] >= pre_s].copy()

    data["treated"] = data[unit_col].isin(treatment_units).astype(int)
    data["post"] = (data[date_col] >= cut).astype(int)
    data[outcome_col] = data[outcome_col].astype(float)

    cells = {
        "tp": data[(data.treated == 1) & (data.post == 0)],
        "tpo": data[(data.treated == 1) & (data.post == 1)],
        "cp": data[(data.treated == 0) & (data.post == 0)],
        "cpo": data[(data.treated == 0) & (data.post == 1)],
    }
    for k, v in cells.items():
        if len(v) < 20:
            return {"error": f"Insufficient data in {k} cell ({len(v)} rows)"}

    def ior(d):
        return float(d[outcome_col].mean()) if len(d) > 0 else np.nan

    ior_tp, ior_tpo = ior(cells["tp"]), ior(cells["tpo"])
    ior_cp, ior_cpo = ior(cells["cp"]), ior(cells["cpo"])
    did_est = (ior_tpo - ior_tp) - (ior_cpo - ior_cp)

    se_delta = np.sqrt(
        sum(_proportion_se(ior(cells[k]), len(cells[k])) ** 2 for k in ("tp", "tpo", "cp", "cpo"))
    )
    z_crit = norm.ppf(1 - alpha / 2)
    p_val = float(2 * norm.sf(abs(did_est / se_delta))) if se_delta > 0 else 1.0

    # Bootstrap CI
    rng = np.random.default_rng(42)  # noqa: F841
    boot_dids = []
    for i in range(n_bootstrap):
        b_tp = cells["tp"].sample(len(cells["tp"]), replace=True, random_state=i)
        b_tpo = cells["tpo"].sample(len(cells["tpo"]), replace=True, random_state=i + 1)
        b_cp = cells["cp"].sample(len(cells["cp"]), replace=True, random_state=i + 2)
        b_cpo = cells["cpo"].sample(len(cells["cpo"]), replace=True, random_state=i + 3)
        boot_dids.append((ior(b_tpo) - ior(b_tp)) - (ior(b_cpo) - ior(b_cp)))
    boot_arr = np.array(boot_dids)
    se_boot = float(np.std(boot_arr))
    ci_boot_lo = float(np.percentile(boot_arr, 100 * alpha / 2))
    ci_boot_hi = float(np.percentile(boot_arr, 100 * (1 - alpha / 2)))

    # Parallel trends regression test
    pre_data = data[data.post == 0].copy()
    pre_data["t"] = (pre_data[date_col] - pre_s).dt.days.astype(float)
    pt_coef, pt_p = 0.0, 1.0
    try:
        X_pt = np.column_stack(
            [
                np.ones(len(pre_data)),
                pre_data["t"].values,
                pre_data["treated"].values,
                pre_data["treated"].values * pre_data["t"].values,
            ]
        )
        y_pt = pre_data[outcome_col].values
        coefs = np.linalg.lstsq(X_pt, y_pt, rcond=None)[0]
        resid = y_pt - X_pt @ coefs
        sigma2 = np.sum(resid**2) / max(len(y_pt) - 4, 1)
        se_c = np.sqrt(np.diag(sigma2 * np.linalg.pinv(X_pt.T @ X_pt)))
        pt_coef = float(coefs[3])
        pt_p = float(2 * scipy_stats.t.sf(abs(pt_coef / se_c[3]), df=len(y_pt) - 4))
    except Exception as e:
        logger.debug("PT test failed: %s", e)

    # Event study
    event_study = []
    for wk in range(-12, 17):
        w0 = cut + pd.Timedelta(weeks=wk)
        w1 = w0 + pd.Timedelta(weeks=1)
        tw = data[(data.treated == 1) & data[date_col].between(w0, w1)]
        cw = data[(data.treated == 0) & data[date_col].between(w0, w1)]
        if len(tw) >= 15 and len(cw) >= 15:
            gap = ior(tw) - ior(cw)
            se_g = np.sqrt(
                _proportion_se(ior(tw), len(tw)) ** 2 + _proportion_se(ior(cw), len(cw)) ** 2
            )
            event_study.append(
                {
                    "week": wk,
                    "gap": round(float(gap) * 100, 4),
                    "gap_ci_lo": round((gap - 1.96 * se_g) * 100, 4),
                    "gap_ci_hi": round((gap + 1.96 * se_g) * 100, 4),
                    "n_treat": len(tw),
                    "n_ctrl": len(cw),
                }
            )

    # TWFE
    twfe_result = {}
    if run_twfe:
        try:
            data["week"] = data[date_col].dt.to_period("W").apply(lambda x: x.start_time)
            panel = data.groupby([unit_col, "week", "treated"])[outcome_col].mean().reset_index()
            panel["D"] = panel["treated"] * (panel["week"] >= cut).astype(int)
            for col2, gb in [("y_dm", outcome_col), ("D_dm", "D")]:
                panel[col2] = (
                    panel[gb]
                    - panel.groupby(unit_col)[gb].transform("mean")
                    - panel.groupby("week")[gb].transform("mean")
                    + panel[gb].mean()
                )
            X_tw = panel["D_dm"].values
            y_tw = panel["y_dm"].values
            if np.sum(X_tw**2) > 1e-10:
                twfe_c = float(np.dot(X_tw, y_tw) / np.dot(X_tw, X_tw))
                resid2 = y_tw - X_tw * twfe_c
                se_tw = float(
                    np.sqrt(np.sum(resid2**2) / max(len(y_tw) - 2, 1) / np.dot(X_tw, X_tw))
                )
                t_tw = twfe_c / se_tw if se_tw > 0 else 0
                p_tw = float(2 * scipy_stats.t.sf(abs(t_tw), df=max(len(y_tw) - 2, 1)))
                twfe_result = {
                    "twfe_estimate_pp": round(twfe_c * 100, 4),
                    "twfe_se_pp": round(se_tw * 100, 4),
                    "twfe_p_value": round(p_tw, 5),
                    "twfe_significant": bool(p_tw < alpha),
                }
        except Exception as e:
            logger.debug("TWFE failed: %s", e)

    return {
        "method": "did_v2",
        "unit_col": unit_col,
        "treatment_units": treatment_units,
        "control_units": control_units,
        "cutoff_date": cutoff_date,
        "pre_start": pre_start,
        "ior_treat_pre": round(ior_tp, 5),
        "ior_treat_post": round(ior_tpo, 5),
        "ior_ctrl_pre": round(ior_cp, 5),
        "ior_ctrl_post": round(ior_cpo, 5),
        "did_estimate_pp": round(did_est * 100, 4),
        "did_se_delta_pp": round(se_delta * 100, 4),
        "did_se_bootstrap_pp": round(se_boot * 100, 4),
        "ci_delta_pp": [
            round((did_est - z_crit * se_delta) * 100, 4),
            round((did_est + z_crit * se_delta) * 100, 4),
        ],
        "ci_bootstrap_pp": [round(ci_boot_lo * 100, 4), round(ci_boot_hi * 100, 4)],
        "p_value": round(p_val, 5),
        "is_significant": bool(p_val < alpha),
        "n_bootstrap": n_bootstrap,
        "parallel_trends_coef": round(pt_coef * 100, 5),
        "parallel_trends_p": round(pt_p, 4),
        "parallel_trends_ok": bool(pt_p > 0.10),
        "parallel_trends_note": (
            f"✅ Parallel trends holds (p={pt_p:.3f})"
            if pt_p > 0.10
            else f"⚠️ Parallel trends VIOLATED (p={pt_p:.3f}) — DiD estimate may be biased."
        ),
        "event_study": event_study,
        **twfe_result,
        "n_treat_pre": len(cells["tp"]),
        "n_treat_post": len(cells["tpo"]),
        "n_ctrl_pre": len(cells["cp"]),
        "n_ctrl_post": len(cells["cpo"]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. INTERRUPTED TIME SERIES
# ─────────────────────────────────────────────────────────────────────────────


def run_its_enhanced(
    series: pd.Series,  # DatetimeIndex, float values (e.g. daily IOR)
    cutoff_date: str,
    pre_start: str = None,
    post_end: str = None,
    outcome_name: str = "metric",
) -> Dict:
    s = series.copy()
    if not isinstance(s.index, pd.DatetimeIndex):
        try:
            s.index = pd.to_datetime(s.index)
        except Exception:
            return {"error": "series must have a DatetimeIndex"}

    cut = pd.Timestamp(cutoff_date)
    if pre_start:
        s = s[s.index >= pd.Timestamp(pre_start)]
    if post_end:
        s = s[s.index <= pd.Timestamp(post_end)]
    s = s.dropna().sort_index()

    if len(s) < 20:
        return {"error": f"Insufficient data ({len(s)} points — need ≥20)"}

    n = len(s)
    t = np.arange(n, dtype=float)
    D = (s.index >= cut).astype(float).values
    Dt = t * D

    X = np.column_stack([np.ones(n), t, D, Dt])
    y = s.values.astype(float)

    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    y_hat = X @ coef
    resid = y - y_hat
    sigma2 = np.sum(resid**2) / max(n - 4, 1)
    XtX_inv = np.linalg.pinv(X.T @ X)
    se_coef = np.sqrt(np.diag(sigma2 * XtX_inv))

    b0, b1, b2, b3 = coef
    se_b2, se_b3 = se_coef[2], se_coef[3]

    def _t_p(b, se):
        t_stat = b / se if se > 0 else 0
        p = float(2 * scipy_stats.t.sf(abs(t_stat), df=n - 4))
        return round(b * 100, 5), round(se * 100, 5), round(t_stat, 3), round(p, 6)

    lc_pp, lc_se, lc_t, lc_p = _t_p(b2, se_b2)
    sc_pp, sc_se, sc_t, sc_p = _t_p(b3, se_b3)

    ss_res = np.sum(resid**2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    # Counterfactual (no intervention after cutoff)
    X_cf = np.column_stack([np.ones(n), t, np.zeros(n), np.zeros(n)])
    y_cf = X_cf @ coef

    post_mask = s.index >= cut
    avg_obs = float(y[post_mask].mean())
    avg_cf = float(y_cf[post_mask].mean())
    avg_lift = (avg_obs - avg_cf) * 100

    return {
        "method": "its_enhanced",
        "outcome": outcome_name,
        "cutoff_date": cutoff_date,
        "n_pre": int(np.sum(~post_mask)),
        "n_post": int(np.sum(post_mask)),
        "model_r2": round(r2, 4),
        "pre_slope_pp_day": round(b1 * 100, 6),
        "level_change_pp": lc_pp,
        "level_se_pp": lc_se,
        "level_t_stat": lc_t,
        "level_p_value": lc_p,
        "level_significant": bool(lc_p < 0.05),
        "slope_change_pp_day": sc_pp,
        "slope_se_pp": sc_se,
        "slope_t_stat": sc_t,
        "slope_p_value": sc_p,
        "slope_significant": bool(sc_p < 0.05),
        "avg_observed_post": round(avg_obs, 6),
        "avg_counterfactual": round(avg_cf, 6),
        "avg_lift_pp": round(avg_lift, 4),
        "fitted_values": y_hat.tolist(),
        "counterfactual": y_cf.tolist(),
        "dates": [str(d.date()) for d in s.index],
        "actual_values": y.tolist(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. PROPENSITY SCORE MATCHING (full)
# ─────────────────────────────────────────────────────────────────────────────


def run_psm_full(
    df: pd.DataFrame,
    outcome_col: str = "converted_to_order",
    treatment_col: str = "variant",
    control_label: str = "control",
    covariate_cols: Optional[List[str]] = None,
    caliper: float = 0.10,
    n_logit_iters: int = 300,
    alpha: float = 0.05,
) -> Dict:
    from scipy.special import expit as sigmoid

    data = df.copy()
    data["treated"] = (data[treatment_col] != control_label).astype(int)
    data[outcome_col] = data[outcome_col].astype(float)

    cov_cols = covariate_cols or [
        c
        for c in [
            "account_segment",
            "platform",
            "has_billing_profile",
            "lifetime_orders",
            "country",
        ]
        if c in data.columns
    ]

    # Encode covariates
    X_raw = pd.get_dummies(data[cov_cols].fillna("Unknown"), drop_first=True).astype(float)
    if X_raw.empty:
        return {"error": "No valid covariate columns after encoding"}

    X = np.column_stack([np.ones(len(X_raw)), X_raw.values])
    y = data["treated"].values.astype(float)

    # Logistic regression (SGD)
    theta = np.zeros(X.shape[1])
    lr = 0.05
    for _ in range(n_logit_iters):
        pred = sigmoid(X @ theta)
        grad = X.T @ (pred - y) / len(y)
        theta -= lr * grad

    data["propensity"] = sigmoid(X @ theta)

    # 1:1 nearest-neighbour matching
    treated_idx = data[data.treated == 1].index.tolist()
    control_idx = data[data.treated == 0].index.tolist()
    matched_pairs: List[Tuple[int, int]] = []
    used = set()

    for t_idx in treated_idx:
        p_t = data.loc[t_idx, "propensity"]
        best_c, best_d = None, np.inf
        for c_idx in control_idx:
            if c_idx in used:
                continue
            d = abs(p_t - data.loc[c_idx, "propensity"])
            if d < best_d:
                best_d, best_c = d, c_idx
        if best_c is not None and best_d < caliper:
            matched_pairs.append((t_idx, best_c))
            used.add(best_c)

    if len(matched_pairs) < 20:
        return {
            "error": f"Only {len(matched_pairs)} matched pairs (caliper={caliper}). "
            "Try widening caliper or check propensity overlap."
        }

    t_idx_m = [p[0] for p in matched_pairs]
    c_idx_m = [p[1] for p in matched_pairs]
    t_out = data.loc[t_idx_m, outcome_col].values
    c_out = data.loc[c_idx_m, outcome_col].values
    att = float(t_out.mean() - c_out.mean())

    p_val_res = _z_test(float(c_out.mean()), len(c_out), float(t_out.mean()), len(t_out), alpha)

    # SMD before and after
    col_names = list(X_raw.columns)
    smd_before, smd_after = [], []
    for col_idx, col_name in enumerate(col_names):
        raw_t = X_raw.values[data.treated == 1, col_idx]
        raw_c = X_raw.values[data.treated == 0, col_idx]
        mat_t = X_raw.values[t_idx_m, col_idx]
        mat_c = X_raw.values[c_idx_m, col_idx]
        pool_sd = np.sqrt((raw_t.std() ** 2 + raw_c.std() ** 2) / 2) or 1.0
        smd_before.append(
            {"covariate": col_name, "smd": round(abs(raw_t.mean() - raw_c.mean()) / pool_sd, 4)}
        )
        smd_after.append(
            {"covariate": col_name, "smd": round(abs(mat_t.mean() - mat_c.mean()) / pool_sd, 4)}
        )

    max_smd = max(s["smd"] for s in smd_after)

    return {
        "method": "psm_full",
        "outcome_col": outcome_col,
        "n_treated_total": len(treated_idx),
        "n_matched_pairs": len(matched_pairs),
        "match_rate": round(len(matched_pairs) / max(len(treated_idx), 1), 3),
        "caliper": caliper,
        "att_pp": round(att * 100, 4),
        "ior_treated": round(float(t_out.mean()), 5),
        "ior_control": round(float(c_out.mean()), 5),
        "delta_pp": p_val_res["delta_pp"],
        "ci_lo_pp": p_val_res["ci_lo_pp"],
        "ci_hi_pp": p_val_res["ci_hi_pp"],
        "p_value": p_val_res["p_value"],
        "is_significant": p_val_res["is_significant"],
        "smd_before": smd_before,
        "smd_after": smd_after,
        "max_smd_after": round(max_smd, 4),
        "balance_ok": bool(max_smd < 0.10),
        "balance_note": (
            "✅ Good balance (max SMD < 0.10)"
            if max_smd < 0.10
            else f"⚠️ Poor balance (max SMD={max_smd:.3f}). Results may be biased."
        ),
        "covariates": col_names,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. SYNTHETIC CONTROL v2
# ─────────────────────────────────────────────────────────────────────────────


def run_synthetic_control_v2(
    df: pd.DataFrame,
    treatment_unit: str,
    donor_units: List[str],
    cutoff_date: str,
    pre_start: str,
    unit_col: str = "account_segment",
    outcome_col: str = "converted_to_order",
    date_col: str = "created_at",
    pre_rmspe_threshold: float = 0.015,
    n_placebo_permutations: int = min(20, 5),  # donor-placebo count
) -> Dict:
    try:
        from scipy.optimize import minimize as _minimize
    except ImportError:
        return {"error": "scipy.optimize required"}

    data = df.copy()
    data[date_col] = pd.to_datetime(data[date_col])
    data[outcome_col] = data[outcome_col].astype(float)
    cut = pd.Timestamp(cutoff_date)
    pre = pd.Timestamp(pre_start)  # noqa: F841

    # Build weekly aggregated panel
    data["week"] = data[date_col].dt.to_period("W").apply(lambda x: x.start_time)
    panel = (
        data[data[unit_col].isin([treatment_unit] + donor_units)]
        .groupby(["week", unit_col])[outcome_col]
        .mean()
        .reset_index()
    )

    weeks = sorted(panel["week"].unique())
    pre_wk = [w for w in weeks if w < cut]
    post_wk = [w for w in weeks if w >= cut]

    if len(pre_wk) < 4 or len(post_wk) < 2:
        return {"error": f"Insufficient weeks: {len(pre_wk)} pre, {len(post_wk)} post"}

    def _series(unit, wk_list) -> np.ndarray:
        s = panel[(panel[unit_col] == unit) & panel["week"].isin(wk_list)]
        s = s.set_index("week").reindex(wk_list)[outcome_col].fillna(method="ffill").values
        return s.astype(float)

    Y_tr_pre = _series(treatment_unit, pre_wk)
    donors_pre = np.column_stack([_series(d, pre_wk) for d in donor_units])

    def _loss(w):
        synth = donors_pre @ w
        return float(np.mean((Y_tr_pre - synth) ** 2))

    n_d = len(donor_units)
    w0 = np.ones(n_d) / n_d
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0, 1)] * n_d
    res = _minimize(
        _loss,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-10, "maxiter": 1000},
    )
    W = res.x

    synth_pre = donors_pre @ W
    pre_rmspe = float(np.sqrt(np.mean((Y_tr_pre - synth_pre) ** 2)))
    fit_warn = pre_rmspe > pre_rmspe_threshold

    Y_tr_post = _series(treatment_unit, post_wk)
    donors_post = np.column_stack([_series(d, post_wk) for d in donor_units])
    synth_post = donors_post @ W
    post_rmspe = float(np.sqrt(np.mean((Y_tr_post - synth_post) ** 2)))
    gap_post = Y_tr_post - synth_post
    avg_lift_pp = float(np.mean(gap_post) * 100)

    rmspe_ratio = post_rmspe / pre_rmspe if pre_rmspe > 0 else 0

    # Permutation inference (donor placebos)
    placebo_ratios = []
    for d in donor_units[:n_placebo_permutations]:
        other_donors = [x for x in donor_units if x != d]
        if not other_donors:
            continue
        Y_d_pre = _series(d, pre_wk)
        D_pre = np.column_stack([_series(x, pre_wk) for x in other_donors])
        res_p = _minimize(
            lambda w: float(np.mean((Y_d_pre - D_pre @ w) ** 2)),
            np.ones(len(other_donors)) / len(other_donors),
            method="SLSQP",
            bounds=[(0, 1)] * len(other_donors),
            constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1}],
            options={"ftol": 1e-10, "maxiter": 500},
        )
        W_p = res_p.x
        pre_r_p = float(np.sqrt(np.mean((Y_d_pre - D_pre @ W_p) ** 2)))
        if pre_r_p > 1e-6:
            Y_d_post = _series(d, post_wk)
            D_post = np.column_stack([_series(x, post_wk) for x in other_donors])
            post_r_p = float(np.sqrt(np.mean((Y_d_post - D_post @ W_p) ** 2)))
            placebo_ratios.append(post_r_p / pre_r_p)

    p_value_perm = (
        float(np.mean([r >= rmspe_ratio for r in placebo_ratios])) if placebo_ratios else None
    )

    return {
        "method": "synthetic_control_v2",
        "treatment_unit": treatment_unit,
        "donor_units": donor_units,
        "cutoff_date": cutoff_date,
        "donor_weights": {d: round(float(W[i]), 4) for i, d in enumerate(donor_units)},
        "pre_rmspe": round(pre_rmspe, 6),
        "post_rmspe": round(post_rmspe, 6),
        "rmspe_ratio": round(rmspe_ratio, 4),
        "fit_warning": fit_warn,
        "fit_note": (
            f"⚠️ Pre-RMSPE={pre_rmspe:.4f} exceeds threshold ({pre_rmspe_threshold}) — "
            "fit quality too poor to extrapolate"
            if fit_warn
            else f"✅ Good pre-period fit (RMSPE={pre_rmspe:.4f})"
        ),
        "avg_lift_pp": round(avg_lift_pp, 4),
        "gap_series_pp": [round(g * 100, 4) for g in gap_post],
        "n_pre_weeks": len(pre_wk),
        "n_post_weeks": len(post_wk),
        "permutation_p_value": round(p_value_perm, 3) if p_value_perm is not None else None,
        "n_placebo_donors": len(placebo_ratios),
        "pre_series": Y_tr_pre.tolist(),
        "synthetic_pre": synth_pre.tolist(),
        "post_series": Y_tr_post.tolist(),
        "synthetic_post": synth_post.tolist(),
        "weeks": [str(w.date()) for w in pre_wk + post_wk],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. CAUSAL MEDIATION ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────


def run_mediation_analysis(
    df: pd.DataFrame,
    treatment_col: str = "variant",
    mediator_col: str = "has_billing_profile",
    outcome_col: str = "converted_to_order",
    control_label: str = "control",
    n_bootstrap: int = 1_000,
    alpha: float = 0.05,
) -> Dict:
    data = df.copy()
    data["treated"] = (data[treatment_col] != control_label).astype(int)
    data[outcome_col] = data[outcome_col].astype(float)
    data[mediator_col] = data[mediator_col].astype(float)
    data = data.dropna(subset=["treated", mediator_col, outcome_col])

    if len(data) < 50:
        return {"error": f"Insufficient data ({len(data)} rows)"}

    t_flag = data["treated"].values
    M = data[mediator_col].values
    Y = data[outcome_col].values

    def _ols_coef(X, y):
        X_aug = np.column_stack([np.ones(len(X)), X])
        coef, *_ = np.linalg.lstsq(X_aug, y, rcond=None)
        return coef

    # Stage 1: M ~ T  →  α = treatment effect on mediator
    coef_m = _ols_coef(t_flag.reshape(-1, 1), M)
    alpha_m = float(coef_m[1])  # coefficient on treated

    # Stage 2: Y ~ T + M  →  β = mediator effect on outcome (controlling for T)
    coef_y = _ols_coef(np.column_stack([t_flag, M]), Y)
    ade = float(coef_y[1])  # direct effect (coefficient on treated)
    beta_m = float(coef_y[2])  # mediator coefficient

    acme = alpha_m * beta_m
    total = ade + acme
    prop_mediated = acme / total if abs(total) > 1e-8 else 0.0

    # Bootstrap SE for ACME
    boot_acme = []
    for i in range(n_bootstrap):
        idx = np.random.default_rng(i).integers(0, len(data), len(data))
        b_t = t_flag[idx]
        b_m = M[idx]
        b_y = Y[idx]
        b_cm = _ols_coef(b_t.reshape(-1, 1), b_m)
        b_cy = _ols_coef(np.column_stack([b_t, b_m]), b_y)
        boot_acme.append(float(b_cm[1]) * float(b_cy[2]))
    boot_arr = np.array(boot_acme)
    se_acme = float(np.std(boot_arr))
    z_crit = norm.ppf(1 - alpha / 2)  # noqa: F841
    ci_lo_acme = float(np.percentile(boot_arr, 100 * alpha / 2))
    ci_hi_acme = float(np.percentile(boot_arr, 100 * (1 - alpha / 2)))
    p_acme = float(2 * norm.sf(abs(acme / se_acme))) if se_acme > 0 else 1.0

    return {
        "method": "mediation",
        "treatment_col": treatment_col,
        "mediator_col": mediator_col,
        "outcome_col": outcome_col,
        "n": len(data),
        "total_effect_pp": round(total * 100, 4),
        "direct_effect_pp": round(ade * 100, 4),  # ADE
        "indirect_effect_pp": round(acme * 100, 4),  # ACME
        "indirect_se_pp": round(se_acme * 100, 4),
        "indirect_ci_lo_pp": round(ci_lo_acme * 100, 4),
        "indirect_ci_hi_pp": round(ci_hi_acme * 100, 4),
        "indirect_p_value": round(p_acme, 6),
        "indirect_significant": bool(p_acme < alpha),
        "proportion_mediated": round(prop_mediated, 4),
        "alpha_treatment_on_mediator": round(alpha_m, 5),
        "beta_mediator_on_outcome": round(beta_m, 5),
        "n_bootstrap": n_bootstrap,
        "interpretation": (
            f"{mediator_col} mediates {prop_mediated:.0%} of the treatment effect "
            f"(ACME={acme*100:+.3f}pp, p={p_acme:.4f})"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. REGRESSION DISCONTINUITY
# ─────────────────────────────────────────────────────────────────────────────


def run_rdd_enhanced(
    df: pd.DataFrame,
    running_var: str,
    cutoff: float,
    outcome_col: str = "converted_to_order",
    bandwidth: Optional[float] = None,  # None = IK rule-of-thumb
    alpha: float = 0.05,
) -> Dict:
    data = df.copy()
    if running_var not in data.columns:
        return {"error": f"Running variable '{running_var}' not found"}
    data = data.dropna(subset=[running_var, outcome_col])
    data["x"] = data[running_var].astype(float) - cutoff  # centre at 0
    data["treated"] = (data["x"] >= 0).astype(int)
    data[outcome_col] = data[outcome_col].astype(float)

    # IK-style bandwidth: 1.5× std of x within ±2 std
    if bandwidth is None:
        sigma = float(data["x"].std())
        bandwidth = 1.5 * sigma
        bw_auto = True
    else:
        bw_auto = False

    window = data[data["x"].abs() <= bandwidth].copy()
    left = window[window.treated == 0]
    right = window[window.treated == 1]

    if len(left) < 10 or len(right) < 10:
        return {
            "error": f"Insufficient data near cutoff (bw={bandwidth:.3f}): "
            f"left={len(left)}, right={len(right)}"
        }

    def _local_linear(sub: pd.DataFrame) -> Tuple[float, float, float]:
        X = np.column_stack([np.ones(len(sub)), sub["x"].values])
        y = sub[outcome_col].values
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ coef
        se = float(np.sqrt(np.sum(resid**2) / max(len(sub) - 2, 1)))
        return float(coef[0]), float(coef[1]), se

    mu_left, sl_left, se_left = _local_linear(left)
    mu_right, sl_right, se_right = _local_linear(right)

    disc = mu_right - mu_left
    se_disc = np.sqrt(
        (se_right * np.sqrt(len(right))) ** 2 / len(right)
        + (se_left * np.sqrt(len(left))) ** 2 / len(left)
    )
    se_disc = max(se_disc, 1e-10)
    z_stat = disc / se_disc
    p_val = float(2 * norm.sf(abs(z_stat)))

    # McCrary density test proxy: count observations in bins near cutoff
    eps = bandwidth / 5
    n_left_near = int((data["x"].between(-eps, 0)).sum())
    n_right_near = int((data["x"].between(0, eps)).sum())
    density_ratio = n_right_near / n_left_near if n_left_near > 0 else None
    manipulation_flag = density_ratio is not None and (density_ratio > 2.0 or density_ratio < 0.5)

    return {
        "method": "rdd_enhanced",
        "running_var": running_var,
        "cutoff": cutoff,
        "bandwidth": round(bandwidth, 4),
        "bandwidth_auto": bw_auto,
        "n_left": len(left),
        "n_right": len(right),
        "mu_left": round(mu_left, 5),
        "mu_right": round(mu_right, 5),
        "discontinuity_pp": round(disc * 100, 4),
        "disc_se_pp": round(se_disc * 100, 4),
        "z_stat": round(z_stat, 4),
        "p_value": round(p_val, 6),
        "is_significant": bool(p_val < alpha),
        "ci_lo_pp": round((disc - 1.96 * se_disc) * 100, 4),
        "ci_hi_pp": round((disc + 1.96 * se_disc) * 100, 4),
        "density_ratio": round(density_ratio, 3) if density_ratio else None,
        "manipulation_flag": manipulation_flag,
        "manipulation_note": (
            "⚠️ Possible manipulation near cutoff (density ratio={:.2f})".format(density_ratio)
            if manipulation_flag
            else "✅ No evidence of cutoff manipulation"
        ),
        "left_slope": round(sl_left, 6),
        "right_slope": round(sl_right, 6),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. SIMPSON'S PARADOX DETECTOR
# ─────────────────────────────────────────────────────────────────────────────


def detect_simpsons_paradox(
    df: pd.DataFrame,
    outcome_col: str = "converted_to_order",
    treatment_col: str = "variant",
    control_label: str = "control",
    dimensions: Optional[List[str]] = None,
    alpha: float = 0.05,
) -> Dict:
    data = df.copy()
    data[outcome_col] = data[outcome_col].astype(float)

    dims = dimensions or [
        c for c in ["account_segment", "platform", "country", "category"] if c in data.columns
    ]

    treatments = [v for v in data[treatment_col].unique() if v != control_label]
    if not treatments:
        return {"error": "No treatment variant found"}
    trt = treatments[0]

    ctrl_all = data[data[treatment_col] == control_label]
    trt_all = data[data[treatment_col] == trt]
    if len(ctrl_all) < 30 or len(trt_all) < 30:
        return {"error": "Insufficient data for paradox detection"}

    overall_delta = float(trt_all[outcome_col].mean() - ctrl_all[outcome_col].mean())
    overall_sig = len(data) > 200  # rough proxy  # noqa: F841

    paradoxes, slices = [], []
    for dim in dims:
        if dim not in data.columns:
            continue
        for level in data[dim].dropna().unique():
            sub = data[data[dim] == level]
            c_sub = sub[sub[treatment_col] == control_label]
            t_sub = sub[sub[treatment_col] == trt]
            if len(c_sub) < 20 or len(t_sub) < 20:
                continue

            seg_delta = float(t_sub[outcome_col].mean() - c_sub[outcome_col].mean())
            seg_n = len(sub)

            # Paradox: aggregate positive but segment negative (or vice versa)
            reversal = overall_delta * seg_delta < 0
            slices.append(
                {
                    "dimension": dim,
                    "level": str(level),
                    "n": seg_n,
                    "ior_ctrl": round(float(c_sub[outcome_col].mean()), 5),
                    "ior_trt": round(float(t_sub[outcome_col].mean()), 5),
                    "delta_pp": round(seg_delta * 100, 4),
                    "overall_delta_pp": round(overall_delta * 100, 4),
                    "reversal": reversal,
                    "pct_of_data": round(seg_n / len(data), 3),
                }
            )
            if reversal:
                paradoxes.append(
                    {
                        "dimension": dim,
                        "level": str(level),
                        "segment_delta_pp": round(seg_delta * 100, 4),
                        "overall_delta_pp": round(overall_delta * 100, 4),
                        "n_in_segment": seg_n,
                        "pct_of_data": round(seg_n / len(data), 3),
                        "severity": "critical" if seg_n / len(data) > 0.20 else "warning",
                    }
                )

    paradoxes.sort(key=lambda x: x["pct_of_data"], reverse=True)

    return {
        "method": "simpsons_paradox_detector",
        "treatment": trt,
        "overall_delta_pp": round(overall_delta * 100, 4),
        "n_total": len(data),
        "n_paradoxes": len(paradoxes),
        "paradoxes": paradoxes,
        "all_slices": slices,
        "verdict": (
            f"⚠️ Simpson's paradox detected in {len(paradoxes)} segment(s). "
            f"Aggregate direction ({'+' if overall_delta > 0 else ''}{overall_delta*100:.2f}pp) "
            f"is reversed in these segments."
            if paradoxes
            else "✅ No Simpson's paradox detected. Segment effects are consistent with aggregate."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. DISTRIBUTION SHIFT DETECTION
# ─────────────────────────────────────────────────────────────────────────────


def detect_distribution_shift(
    df_pre: pd.DataFrame,
    df_post: pd.DataFrame,
    columns: Optional[List[str]] = None,
    alpha: float = 0.05,
) -> Dict:
    cols = columns or list(set(df_pre.columns) & set(df_post.columns))
    cols = [c for c in cols if c not in ("created_at", "inquiry_id", "buyer_id")]

    results = []
    for col in cols:
        try:
            pre_vals = df_pre[col].dropna()
            post_vals = df_post[col].dropna()
            if len(pre_vals) < 10 or len(post_vals) < 10:
                continue

            is_numeric = pd.api.types.is_numeric_dtype(pre_vals)

            if is_numeric:
                stat, p = scipy_stats.ks_2samp(
                    pre_vals.values.astype(float), post_vals.values.astype(float)
                )
                test = "ks"
            else:
                cats = list(set(pre_vals.unique()) | set(post_vals.unique()))
                pre_cnt = [int((pre_vals == c).sum()) for c in cats]
                post_cnt = [int((post_vals == c).sum()) for c in cats]
                # only rows where both counts > 0 for chi2
                valid = [(p, q) for p, q in zip(pre_cnt, post_cnt) if p + q > 0]
                if not valid:
                    continue
                _, p = scipy_stats.chi2_contingency(
                    np.array([[v[0] for v in valid], [v[1] for v in valid]])
                )[:2]
                stat = float(
                    abs(
                        np.array([v[0] for v in valid]) / sum(v[0] for v in valid)
                        - np.array([v[1] for v in valid]) / sum(v[1] for v in valid)
                    ).max()
                )
                test = "chi2"

            results.append(
                {
                    "column": col,
                    "test": test,
                    "statistic": round(float(stat), 4),
                    "p_value": round(float(p), 6),
                    "shifted": bool(p < alpha),
                    "severity": "critical" if p < 0.001 else "warning" if p < alpha else "ok",
                }
            )
        except Exception as e:
            logger.debug("Shift detect failed for %s: %s", col, e)

    shifted = [r for r in results if r["shifted"]]
    return {
        "method": "distribution_shift",
        "n_columns": len(results),
        "n_shifted": len(shifted),
        "columns": results,
        "shifted_columns": shifted,
        "overall_severity": (
            "critical"
            if any(r["severity"] == "critical" for r in shifted)
            else "warning" if shifted else "ok"
        ),
    }


__all__ = [
    "run_did_v2",
    "run_its_enhanced",
    "run_psm_full",
    "run_synthetic_control_v2",
    "run_mediation_analysis",
    "run_rdd_enhanced",
    "detect_simpsons_paradox",
    "detect_distribution_shift",
]
