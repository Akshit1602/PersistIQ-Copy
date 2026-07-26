from __future__ import annotations

import warnings
from typing import Dict, Optional

import numpy as np
from scipy import stats
from scipy.stats import norm

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# DATA QUALITY UTILITIES
# ─────────────────────────────────────────────────────────────────────────────


def winsorise(arr: np.ndarray, pct: int = 99) -> np.ndarray:
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return arr
    upper = np.percentile(arr, pct)
    lower = np.percentile(arr, 100 - pct)
    return np.clip(arr, lower, upper)


def safe_val(v, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if x == x else float(default)  # NaN check
    except (TypeError, ValueError):
        return float(default)


# ─────────────────────────────────────────────────────────────────────────────
# PROPORTION TEST (IOR, rate metrics)
# ─────────────────────────────────────────────────────────────────────────────


def proportion_test(
    n_ctrl: int,
    conv_ctrl: int,
    n_treat: int,
    conv_treat: int,
    alpha: float = 0.05,
) -> Dict:

    p_c = conv_ctrl / n_ctrl if n_ctrl > 0 else 0.0
    p_t = conv_treat / n_treat if n_treat > 0 else 0.0
    delta = p_t - p_c
    rel = delta / p_c if p_c > 0 else 0.0

    p_pool = (conv_ctrl + conv_treat) / (n_ctrl + n_treat) if (n_ctrl + n_treat) > 0 else 0.5
    se = (
        np.sqrt(p_pool * (1 - p_pool) * (1 / n_ctrl + 1 / n_treat))
        if (n_ctrl + n_treat) > 0
        else 1.0
    )
    z_stat = delta / se if se > 0 else 0.0
    p_val = 2 * norm.sf(abs(z_stat))

    se_delta = (
        np.sqrt(p_c * (1 - p_c) / n_ctrl + p_t * (1 - p_t) / n_treat)
        if (n_ctrl * n_treat) > 0
        else 0.0
    )
    z_crit = norm.ppf(1 - alpha / 2)
    ci_lo = delta - z_crit * se_delta
    ci_hi = delta + z_crit * se_delta

    h = 2 * np.arcsin(np.sqrt(p_t)) - 2 * np.arcsin(np.sqrt(p_c))

    return {
        "n_control": n_ctrl,
        "n_treatment": n_treat,
        "conv_control": conv_ctrl,
        "conv_treatment": conv_treat,
        "rate_control": round(p_c, 6),
        "rate_treatment": round(p_t, 6),
        "delta_abs": round(delta, 6),
        "delta_rel": round(rel, 6),
        "delta_pp": round(delta * 100, 4),
        "z_stat": round(z_stat, 4),
        "p_value": round(p_val, 6),
        "ci_lo_pp": round(ci_lo * 100, 4),
        "ci_hi_pp": round(ci_hi * 100, 4),
        "ci_lo": round(ci_lo, 6),
        "ci_hi": round(ci_hi, 6),
        "effect_size_h": round(h, 4),
        "is_significant": bool(p_val < alpha),
        "direction": "positive" if delta > 0 else "negative" if delta < 0 else "neutral",
        "alpha": alpha,
        "method": "z_test",
    }


# ─────────────────────────────────────────────────────────────────────────────
# MEANS TEST (AOV, revenue metrics)
# ─────────────────────────────────────────────────────────────────────────────


def means_test(
    ctrl_vals: np.ndarray,
    treat_vals: np.ndarray,
    alpha: float = 0.05,
    apply_winsorise: bool = True,
    winsorise_pct: int = 99,
) -> Dict:
    ctrl_vals = ctrl_vals[~np.isnan(ctrl_vals)]
    treat_vals = treat_vals[~np.isnan(treat_vals)]
    if len(ctrl_vals) < 2 or len(treat_vals) < 2:
        return {"error": "insufficient_data"}

    if apply_winsorise:
        ctrl_vals = winsorise(ctrl_vals, winsorise_pct)
        treat_vals = winsorise(treat_vals, winsorise_pct)

    t_stat, p_val = stats.ttest_ind(ctrl_vals, treat_vals, equal_var=False)
    if np.isnan(p_val):
        p_val = 1.0  # identical arrays or zero variance
    delta_mean = float(treat_vals.mean() - ctrl_vals.mean())
    rel = delta_mean / ctrl_vals.mean() if ctrl_vals.mean() != 0 else 0.0
    pooled_sd = np.sqrt((ctrl_vals.std() ** 2 + treat_vals.std() ** 2) / 2)
    cohens_d = delta_mean / pooled_sd if pooled_sd > 0 else 0.0

    se = np.sqrt(ctrl_vals.var() / len(ctrl_vals) + treat_vals.var() / len(treat_vals))
    z_crit = norm.ppf(1 - alpha / 2)

    return {
        "n_control": len(ctrl_vals),
        "n_treatment": len(treat_vals),
        "mean_control": round(float(ctrl_vals.mean()), 2),
        "mean_treatment": round(float(treat_vals.mean()), 2),
        "delta_abs": round(delta_mean, 2),
        "delta_rel": round(rel, 4),
        "t_stat": round(float(t_stat), 4),
        "p_value": round(float(p_val), 6),
        "ci_lo": round(delta_mean - z_crit * se, 2),
        "ci_hi": round(delta_mean + z_crit * se, 2),
        "effect_size_d": round(cohens_d, 4),
        "is_significant": bool(p_val < alpha),
        "direction": "positive" if delta_mean > 0 else "negative" if delta_mean < 0 else "neutral",
        "alpha": alpha,
        "method": "t_test",
        "winsorised": apply_winsorise,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SAMPLE SIZE & POWER
# ─────────────────────────────────────────────────────────────────────────────


def compute_sample_size(
    baseline_rate: float,
    mde_abs: float,
    alpha: float = 0.05,
    power: float = 0.80,
    n_variants: int = 2,
) -> Dict:
    p1 = baseline_rate
    p2 = np.clip(baseline_rate + mde_abs, 0.001, 0.999)
    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta = norm.ppf(power)
    n = (
        z_alpha * np.sqrt(2 * p1 * (1 - p1)) + z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    ) ** 2 / (mde_abs**2)
    n_per_variant = int(np.ceil(n))
    n_total = n_per_variant * n_variants
    h = abs(2 * np.arcsin(np.sqrt(p2)) - 2 * np.arcsin(np.sqrt(p1)))
    return {
        "baseline_rate": baseline_rate,
        "target_rate": round(p2, 6),
        "mde_abs": mde_abs,
        "mde_rel": round(mde_abs / baseline_rate * 100, 2) if baseline_rate > 0 else 0,
        "alpha": alpha,
        "power": power,
        "n_variants": n_variants,
        "n_per_variant": n_per_variant,
        "n_total": n_total,
        "effect_size_h": round(h, 4),
    }


def compute_duration(
    n_total: int,
    daily_traffic: float,
    traffic_share: float = 1.0,
) -> Dict:
    import pandas as pd

    effective_daily = daily_traffic * traffic_share
    days = int(np.ceil(n_total / effective_daily)) if effective_daily > 0 else 9999
    weeks = round(days / 7, 1)
    return {
        "daily_eligible": round(effective_daily, 1),
        "days_required": days,
        "weeks_required": weeks,
        "end_date": (pd.Timestamp.today() + pd.Timedelta(days=days)).strftime("%Y-%m-%d"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SRM (SAMPLE RATIO MISMATCH)
# ─────────────────────────────────────────────────────────────────────────────


def check_srm(
    variant_counts: Dict[str, int],
    expected_fractions: Optional[Dict[str, float]] = None,
) -> Dict:
    from scipy.stats import chi2 as _chi2

    variants = list(variant_counts.keys())
    counts = np.array([variant_counts[v] for v in variants], dtype=float)
    n_total = counts.sum()
    if expected_fractions is None:
        expected = np.full(len(variants), n_total / len(variants))
    else:
        expected = np.array(
            [expected_fractions.get(v, 1 / len(variants)) * n_total for v in variants]
        )
    chi2_val = float(np.sum((counts - expected) ** 2 / expected))
    p_srm = float(1 - _chi2.cdf(chi2_val, df=len(variants) - 1))
    return {
        "chi2": round(chi2_val, 4),
        "p_value": round(p_srm, 6),
        "srm_detected": p_srm < 0.01,
        "variant_counts": variant_counts,
        "expected_counts": {v: round(e, 1) for v, e in zip(variants, expected)},
    }


# ─────────────────────────────────────────────────────────────────────────────
# OPPORTUNITY SIZING
# ─────────────────────────────────────────────────────────────────────────────


def compute_opportunity(
    monthly_inquiries: float,
    current_ior: float,
    target_ior: float,
    avg_order_value: float,
    avg_gross_margin: float,
    time_horizon_months: float = 12,
) -> Dict:
    current_orders = monthly_inquiries * current_ior
    target_orders = monthly_inquiries * target_ior
    incr_orders_mo = target_orders - current_orders
    incr_rev_mo = incr_orders_mo * avg_order_value
    incr_gm_mo = incr_rev_mo * avg_gross_margin
    h = int(time_horizon_months)
    return {
        "monthly_inquiries": monthly_inquiries,
        "current_ior": current_ior,
        "target_ior": target_ior,
        "ior_gap_pp": round((target_ior - current_ior) * 100, 2),
        "current_orders_monthly": round(current_orders, 1),
        "target_orders_monthly": round(target_orders, 1),
        "incremental_orders_monthly": round(incr_orders_mo, 1),
        "incremental_revenue_monthly": round(incr_rev_mo, 0),
        "incremental_gm_monthly": round(incr_gm_mo, 0),
        f"incremental_orders_{h}mo": round(incr_orders_mo * h, 0),
        f"incremental_revenue_{h}mo": round(incr_rev_mo * h, 0),
        f"incremental_gm_{h}mo": round(incr_gm_mo * h, 0),
        "avg_order_value": avg_order_value,
        "gross_margin": avg_gross_margin,
        "time_horizon_months": time_horizon_months,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SEQUENTIAL TESTING (mSPRT)
# ─────────────────────────────────────────────────────────────────────────────


def compute_msprt_statistic(
    n_ctrl: int,
    conv_ctrl: int,
    n_treat: int,
    conv_treat: int,
    theta: float = 1.0,
) -> Dict:
    p_c = conv_ctrl / n_ctrl if n_ctrl > 0 else 0.5  # noqa: F841
    p_t = conv_treat / n_treat if n_treat > 0 else 0.5  # noqa: F841
    n = n_ctrl + n_treat
    # Simplified e-value approximation for proportions
    if n < 20:
        return {"e_value": 1.0, "boundary_crossed": False, "n": n}
    z = proportion_test(n_ctrl, conv_ctrl, n_treat, conv_treat)["z_stat"]
    # mSPRT e-value: exp(z^2/2 * theta/(1+theta))
    e_val = float(np.exp(z**2 / 2 * theta / (1 + theta)))
    return {
        "e_value": round(e_val, 4),
        "z_stat": round(z, 4),
        "boundary_crossed": e_val >= (1 / 0.05),  # default alpha=0.05
        "n": n,
        "theta": theta,
    }


__all__ = [
    "winsorise",
    "safe_val",
    "proportion_test",
    "means_test",
    "compute_sample_size",
    "compute_duration",
    "check_srm",
    "compute_opportunity",
    "compute_msprt_statistic",
]
