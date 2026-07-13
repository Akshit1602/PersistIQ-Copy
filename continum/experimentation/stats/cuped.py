from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
from scipy import stats

logger = logging.getLogger("continum.experimentation.cuped")


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CupedResult:
    method: str  # "cuped" | "cupac"
    covariate_name: str
    theta: float  # regression coefficient Y ~ X
    covariate_correlation: float  # ρ(Y, X)
    variance_reduction_pct: float  # 100 * (1 - Var_adj / Var_raw)
    variance_raw: float
    variance_adjusted: float
    n_observations: int
    # Adjusted arrays (returned by value so caller owns them)
    y_ctrl_adj: Tuple[float, ...]
    y_treat_adj: Tuple[float, ...]
    # Adjusted summary stats
    mean_ctrl_adj: float
    mean_treat_adj: float
    delta_adj: float
    se_adj: float
    # p-value & CI using adjusted values
    p_value: float
    ci_lo: float
    ci_hi: float
    is_significant: bool
    alpha: float
    # Diagnostics
    warnings: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CupacResult:
    model_name: str
    covariate_correlation: float
    variance_reduction_pct: float
    cuped_result: CupedResult  # underlying CUPED applied to predictions


# ─────────────────────────────────────────────────────────────────────────────
# CUPED
# ─────────────────────────────────────────────────────────────────────────────


def apply_cuped(
    y_ctrl: np.ndarray,
    y_treat: np.ndarray,
    x_ctrl: np.ndarray,
    x_treat: np.ndarray,
    covariate_name: str = "pre_experiment_metric",
    alpha: float = 0.05,
    min_correlation: float = 0.05,
) -> CupedResult:
    y_ctrl = np.asarray(y_ctrl, dtype=float)
    y_treat = np.asarray(y_treat, dtype=float)
    x_ctrl = np.asarray(x_ctrl, dtype=float)
    x_treat = np.asarray(x_treat, dtype=float)

    # Drop NaN pairs
    def _clean(y, x):
        mask = ~(np.isnan(y) | np.isnan(x))
        return y[mask], x[mask]

    y_ctrl, x_ctrl = _clean(y_ctrl, x_ctrl)
    y_treat, x_treat = _clean(y_treat, x_treat)

    warnings_list: List[str] = []
    n_c, n_t = len(y_ctrl), len(y_treat)

    if n_c < 10 or n_t < 10:
        raise ValueError(f"CUPED requires ≥10 obs per arm; got ctrl={n_c}, treat={n_t}")
    if len(x_ctrl) != n_c or len(x_treat) != n_t:
        raise ValueError("y and x arrays must have the same length per arm")

    # ── Estimate theta on pooled sample ──────────────────────────────────────
    y_pool = np.concatenate([y_ctrl, y_treat])
    x_pool = np.concatenate([x_ctrl, x_treat])
    x_mean_pool = float(x_pool.mean())

    cov_xy = float(np.cov(y_pool, x_pool, ddof=1)[0, 1])
    var_x = float(np.var(x_pool, ddof=1))
    theta = cov_xy / var_x if var_x > 1e-12 else 0.0

    rho = float(np.corrcoef(y_pool, x_pool)[0, 1])
    if abs(rho) < min_correlation:
        warnings_list.append(
            f"Low covariate correlation ρ={rho:.3f} — CUPED may not help for '{covariate_name}'"
        )

    # ── Adjust ───────────────────────────────────────────────────────────────
    y_ctrl_adj = y_ctrl - theta * (x_ctrl - x_mean_pool)
    y_treat_adj = y_treat - theta * (x_treat - x_mean_pool)

    var_raw = float(np.var(y_pool, ddof=1))
    var_adj = float(np.var(np.concatenate([y_ctrl_adj, y_treat_adj]), ddof=1))
    var_reduction = (1 - var_adj / var_raw) * 100 if var_raw > 0 else 0.0

    if var_adj > var_raw * 1.02:
        warnings_list.append(
            "Adjusted variance is larger than raw — covariate may be harmful. "
            "Consider using raw estimates."
        )

    # ── Adjusted test (Welch t) ───────────────────────────────────────────────
    delta_adj = float(y_treat_adj.mean() - y_ctrl_adj.mean())
    se_ctrl = float(y_ctrl_adj.std(ddof=1) / np.sqrt(n_c))
    se_treat = float(y_treat_adj.std(ddof=1) / np.sqrt(n_t))
    se_adj = float(np.sqrt(se_ctrl**2 + se_treat**2))

    t_stat, p_val = stats.ttest_ind(y_ctrl_adj, y_treat_adj, equal_var=False)
    p_val = float(p_val)
    z_crit = float(stats.norm.ppf(1 - alpha / 2))
    ci_lo = delta_adj - z_crit * se_adj
    ci_hi = delta_adj + z_crit * se_adj

    logger.info(
        "CUPED[%s]: ρ=%.3f  θ=%.4f  var_reduction=%.1f%%  " "δ_adj=%.4f  p=%.4f",
        covariate_name,
        rho,
        theta,
        var_reduction,
        delta_adj,
        p_val,
    )

    return CupedResult(
        method="cuped",
        covariate_name=covariate_name,
        theta=round(theta, 6),
        covariate_correlation=round(rho, 4),
        variance_reduction_pct=round(var_reduction, 2),
        variance_raw=round(var_raw, 6),
        variance_adjusted=round(var_adj, 6),
        n_observations=n_c + n_t,
        y_ctrl_adj=tuple(y_ctrl_adj.tolist()),
        y_treat_adj=tuple(y_treat_adj.tolist()),
        mean_ctrl_adj=round(float(y_ctrl_adj.mean()), 6),
        mean_treat_adj=round(float(y_treat_adj.mean()), 6),
        delta_adj=round(delta_adj, 6),
        se_adj=round(se_adj, 6),
        p_value=round(p_val, 6),
        ci_lo=round(ci_lo, 6),
        ci_hi=round(ci_hi, 6),
        is_significant=bool(p_val < alpha),
        alpha=alpha,
        warnings=tuple(warnings_list),
    )


# ─────────────────────────────────────────────────────────────────────────────
# CUPAC
# ─────────────────────────────────────────────────────────────────────────────


def apply_cupac(
    y_ctrl: np.ndarray,
    y_treat: np.ndarray,
    features_ctrl: np.ndarray,  # 2-D feature matrix, shape (n_ctrl, n_features)
    features_treat: np.ndarray,  # 2-D feature matrix, shape (n_treat, n_features)
    alpha: float = 0.05,
    model: str = "ridge",  # "ridge" | "lasso" | "linear"
) -> CupacResult:
    try:
        from sklearn.linear_model import Lasso, LinearRegression, Ridge
        from sklearn.model_selection import cross_val_score
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise ImportError("scikit-learn is required for CUPAC: pip install scikit-learn") from exc

    y_ctrl = np.asarray(y_ctrl, dtype=float)
    y_treat = np.asarray(y_treat, dtype=float)
    X_ctrl = np.asarray(features_ctrl, dtype=float)
    X_treat = np.asarray(features_treat, dtype=float)

    # Fit on control only
    scaler = StandardScaler()
    X_ctrl_s = scaler.fit_transform(X_ctrl)
    X_treat_s = scaler.transform(X_treat)

    MODEL_MAP = {
        "ridge": Ridge(alpha=1.0),
        "lasso": Lasso(alpha=0.01),
        "linear": LinearRegression(),
    }
    clf = MODEL_MAP.get(model, Ridge(alpha=1.0))
    clf.fit(X_ctrl_s, y_ctrl)

    # R² on control as quality signal
    cv_scores = cross_val_score(clf, X_ctrl_s, y_ctrl, cv=min(5, len(y_ctrl) // 10), scoring="r2")
    cv_r2 = float(cv_scores.mean())
    logger.info("CUPAC model %s: CV-R²=%.4f", model, cv_r2)

    # Generate predictions for both arms — these become CUPED covariate
    yhat_ctrl = clf.predict(X_ctrl_s)
    yhat_treat = clf.predict(X_treat_s)

    rho = float(np.corrcoef(y_ctrl, yhat_ctrl)[0, 1])

    cuped_res = apply_cuped(
        y_ctrl,
        y_treat,
        yhat_ctrl,
        yhat_treat,
        covariate_name=f"cupac_pred_{model}",
        alpha=alpha,
    )

    return CupacResult(
        model_name=model,
        covariate_correlation=round(rho, 4),
        variance_reduction_pct=cuped_res.variance_reduction_pct,
        cuped_result=cuped_res,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POWER GAIN FROM CUPED
# ─────────────────────────────────────────────────────────────────────────────


def cuped_power_gain(
    rho: float,
    baseline_rate: float,
    mde_abs: float,
    alpha: float = 0.05,
    power: float = 0.80,
    n_variants: int = 2,
) -> Dict:
    from continum.experimentation.stats.statistics import compute_sample_size

    raw = compute_sample_size(baseline_rate, mde_abs, alpha, power, n_variants)
    var_reduction = 1 - rho**2
    n_cuped = int(np.ceil(raw["n_per_variant"] * var_reduction))
    saving_pct = (1 - var_reduction) * 100

    return {
        "rho": round(rho, 4),
        "variance_reduction": round((1 - var_reduction) * 100, 1),
        "n_per_variant_raw": raw["n_per_variant"],
        "n_per_variant_cuped": n_cuped,
        "n_total_raw": raw["n_total"],
        "n_total_cuped": n_cuped * n_variants,
        "sample_saving_pct": round(saving_pct, 1),
        "effective_mde_with_same_n": (
            round(mde_abs / np.sqrt(var_reduction), 6) if var_reduction > 0 else mde_abs
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# DELTA METHOD (ratio metrics — GMV/user, AOV, etc.)
# ─────────────────────────────────────────────────────────────────────────────


def delta_method_ratio(
    num_ctrl: np.ndarray,
    den_ctrl: np.ndarray,
    num_treat: np.ndarray,
    den_treat: np.ndarray,
    alpha: float = 0.05,
    metric_name: str = "ratio_metric",
) -> Dict:
    def _ratio_stats(num, den):
        num = np.asarray(num, dtype=float)
        den = np.asarray(den, dtype=float)
        mask = ~(np.isnan(num) | np.isnan(den) | (den == 0))
        num, den = num[mask], den[mask]
        n = len(num)
        mu_y = float(num.mean())
        mu_x = float(den.mean())
        ratio = mu_y / mu_x if mu_x != 0 else 0.0
        var_y = float(np.var(num, ddof=1))
        var_x = float(np.var(den, ddof=1))
        cov_xy = float(np.cov(num, den, ddof=1)[0, 1])
        # Delta method variance
        if mu_x == 0:
            var_ratio = np.inf
        else:
            var_ratio = (
                var_y / mu_x**2 - 2 * mu_y * cov_xy / mu_x**3 + mu_y**2 * var_x / mu_x**4
            ) / n
        se = float(np.sqrt(max(var_ratio, 0)))
        return ratio, se, n

    r_c, se_c, n_c = _ratio_stats(num_ctrl, den_ctrl)
    r_t, se_t, n_t = _ratio_stats(num_treat, den_treat)

    delta = r_t - r_c
    se_tot = float(np.sqrt(se_c**2 + se_t**2))
    z_stat = delta / se_tot if se_tot > 0 else 0.0
    p_val = float(2 * stats.norm.sf(abs(z_stat)))
    z_crit = float(stats.norm.ppf(1 - alpha / 2))

    return {
        "metric_name": metric_name,
        "ratio_ctrl": round(r_c, 6),
        "ratio_treat": round(r_t, 6),
        "delta": round(delta, 6),
        "delta_rel": round(delta / r_c if r_c != 0 else 0, 4),
        "se": round(se_tot, 6),
        "z_stat": round(z_stat, 4),
        "p_value": round(p_val, 6),
        "ci_lo": round(delta - z_crit * se_tot, 6),
        "ci_hi": round(delta + z_crit * se_tot, 6),
        "is_significant": bool(p_val < alpha),
        "direction": "positive" if delta > 0 else "negative" if delta < 0 else "neutral",
        "n_ctrl": n_c,
        "n_treat": n_t,
        "alpha": alpha,
        "method": "delta_method",
    }


# ─────────────────────────────────────────────────────────────────────────────
# BOOTSTRAP CI (non-parametric fallback)
# ─────────────────────────────────────────────────────────────────────────────


def bootstrap_ci(
    ctrl: np.ndarray,
    treat: np.ndarray,
    stat_fn=None,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 42,
) -> Dict:
    rng = np.random.default_rng(seed)
    ctrl = np.asarray(ctrl[~np.isnan(ctrl)], dtype=float)
    treat = np.asarray(treat[~np.isnan(treat)], dtype=float)

    if stat_fn is None:
        stat_fn = lambda c, t: float(t.mean() - c.mean())  # noqa: E731

    observed = stat_fn(ctrl, treat)

    # Bootstrap distribution
    boot_stats = np.empty(n_boot)
    for i in range(n_boot):
        c_ = rng.choice(ctrl, size=len(ctrl), replace=True)
        t_ = rng.choice(treat, size=len(treat), replace=True)
        boot_stats[i] = stat_fn(c_, t_)

    # Percentile CI (fallback)
    lo_pct = float(np.percentile(boot_stats, alpha / 2 * 100))
    hi_pct = float(np.percentile(boot_stats, (1 - alpha / 2) * 100))

    # BCa correction
    z0 = float(stats.norm.ppf((boot_stats < observed).mean() + 1e-9))
    # Jackknife for acceleration
    jack = np.array(
        [
            stat_fn(np.delete(ctrl, i) if i < len(ctrl) else ctrl, treat)
            for i in range(min(len(ctrl), 200))
        ]
    )
    jack_mean = jack.mean()
    num = np.sum((jack_mean - jack) ** 3)
    den = 6 * np.sum((jack_mean - jack) ** 2) ** 1.5
    accel = float(num / den) if den != 0 else 0.0

    alpha_lo = float(
        stats.norm.cdf(
            z0 + (z0 + stats.norm.ppf(alpha / 2)) / (1 - accel * (z0 + stats.norm.ppf(alpha / 2)))
        )
    )
    alpha_hi = float(
        stats.norm.cdf(
            z0
            + (z0 + stats.norm.ppf(1 - alpha / 2))
            / (1 - accel * (z0 + stats.norm.ppf(1 - alpha / 2)))
        )
    )
    alpha_lo = float(np.clip(alpha_lo, 0.001, 0.499))
    alpha_hi = float(np.clip(alpha_hi, 0.501, 0.999))

    ci_lo_bca = float(np.percentile(boot_stats, alpha_lo * 100))
    ci_hi_bca = float(np.percentile(boot_stats, alpha_hi * 100))

    p_val = float(
        min(1.0, 2 * min((boot_stats >= observed).mean(), (boot_stats <= observed).mean()) + 1e-9)
    )

    return {
        "observed": round(observed, 6),
        "ci_lo_bca": round(ci_lo_bca, 6),
        "ci_hi_bca": round(ci_hi_bca, 6),
        "ci_lo_pct": round(lo_pct, 6),
        "ci_hi_pct": round(hi_pct, 6),
        "p_value": round(p_val, 4),
        "is_significant": bool(p_val < alpha),
        "n_boot": n_boot,
        "boot_se": round(float(boot_stats.std()), 6),
        "method": "bootstrap_bca",
        "alpha": alpha,
    }


__all__ = [
    "CupedResult",
    "CupacResult",
    "apply_cuped",
    "apply_cupac",
    "cuped_power_gain",
    "delta_method_ratio",
    "bootstrap_ci",
]
