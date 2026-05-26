import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm

# ─────────────────────────────────────────────────────────────────────────────
# PROPORTION TEST
# ─────────────────────────────────────────────────────────────────────────────
def proportion_test(
    n_ctrl: int, conv_ctrl: int,
    n_treat: int, conv_treat: int,
    alpha: float = 0.05,
) -> dict:
    """Two-proportion z-test. Returns full result dict."""
    p_c = conv_ctrl  / n_ctrl  if n_ctrl  > 0 else 0
    p_t = conv_treat / n_treat if n_treat > 0 else 0
    delta = p_t - p_c
    rel   = delta / p_c if p_c > 0 else 0

    # Pooled proportion
    p_pool = (conv_ctrl + conv_treat) / (n_ctrl + n_treat)
    se     = np.sqrt(p_pool * (1 - p_pool) * (1/n_ctrl + 1/n_treat)) if (n_ctrl+n_treat) > 0 else 1
    z_stat = delta / se if se > 0 else 0
    p_val  = 2 * norm.sf(abs(z_stat))  # two-tailed

    # 95% CI on the delta
    se_delta = np.sqrt(p_c*(1-p_c)/n_ctrl + p_t*(1-p_t)/n_treat) if (n_ctrl*n_treat) > 0 else 0
    z_crit   = norm.ppf(1 - alpha/2)
    ci_lo    = delta - z_crit * se_delta
    ci_hi    = delta + z_crit * se_delta

    # Cohen's h effect size
    h = 2 * np.arcsin(np.sqrt(p_t)) - 2 * np.arcsin(np.sqrt(p_c))

    return {
        'n_control': n_ctrl, 'n_treatment': n_treat,
        'conv_control': conv_ctrl, 'conv_treatment': conv_treat,
        'rate_control': round(p_c, 6), 'rate_treatment': round(p_t, 6),
        'delta_abs': round(delta, 6), 'delta_rel': round(rel, 6),
        'delta_pp': round(delta * 100, 4),
        'z_stat': round(z_stat, 4), 'p_value': round(p_val, 6),
        'ci_lo_pp': round(ci_lo * 100, 4), 'ci_hi_pp': round(ci_hi * 100, 4),
        'effect_size_h': round(h, 4),
        'is_significant': p_val < alpha,
        'direction': 'positive' if delta > 0 else 'negative' if delta < 0 else 'neutral',
        'alpha': alpha,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MEANS TEST (for GMV, revenue, etc.)
# ─────────────────────────────────────────────────────────────────────────────
def means_test(
    ctrl_vals: np.ndarray,
    treat_vals: np.ndarray,
    alpha: float = 0.05,
    apply_winsorise: bool = True,
) -> dict:
    """
    Welch's t-test for two independent samples.
    apply_winsorise=True clips extreme outliers at CLIENT_SCHEMA winsorise_pct
    before testing — prevents a single $500K Enterprise order from driving
    false significance on GMV metrics.
    """
    ctrl_vals  = ctrl_vals[~np.isnan(ctrl_vals)]
    treat_vals = treat_vals[~np.isnan(treat_vals)]
    if len(ctrl_vals) < 2 or len(treat_vals) < 2:
        return {'error': 'insufficient data'}
    # Winsorise to remove outlier influence before testing
    if apply_winsorise:
        try:
            ctrl_vals  = winsorise(ctrl_vals)
            treat_vals = winsorise(treat_vals)
        except Exception:
            pass

    t_stat, p_val = stats.ttest_ind(ctrl_vals, treat_vals, equal_var=False)
    delta_mean = treat_vals.mean() - ctrl_vals.mean()
    rel        = delta_mean / ctrl_vals.mean() if ctrl_vals.mean() != 0 else 0

    # Cohen's d
    pooled_sd = np.sqrt((ctrl_vals.std()**2 + treat_vals.std()**2) / 2)
    cohens_d  = delta_mean / pooled_sd if pooled_sd > 0 else 0

    # 95% CI
    se = np.sqrt(ctrl_vals.var()/len(ctrl_vals) + treat_vals.var()/len(treat_vals))
    z_crit = norm.ppf(1 - alpha/2)
    return {
        'n_control': len(ctrl_vals), 'n_treatment': len(treat_vals),
        'mean_control': round(ctrl_vals.mean(), 2), 'mean_treatment': round(treat_vals.mean(), 2),
        'delta_mean': round(delta_mean, 2), 'delta_rel': round(rel, 4),
        't_stat': round(t_stat, 4), 'p_value': round(p_val, 6),
        'ci_lo': round(delta_mean - z_crit*se, 2),
        'ci_hi': round(delta_mean + z_crit*se, 2),
        'effect_size_d': round(cohens_d, 4),
        'is_significant': p_val < alpha,
        'direction': 'positive' if delta_mean > 0 else 'negative' if delta_mean < 0 else 'neutral',
        'alpha': alpha,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POWER CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────
def compute_sample_size(
    baseline_rate: float,
    mde_abs: float,       # absolute MDE (e.g. 0.01 = 1pp)
    alpha: float = 0.05,
    power: float = 0.80,
    n_variants: int = 2,  # control + treatment
) -> dict:
    """Sample size per variant for a two-proportion test."""
    p1 = baseline_rate
    p2 = baseline_rate + mde_abs
    p2 = np.clip(p2, 0.001, 0.999)

    z_alpha = norm.ppf(1 - alpha/2)   # two-tailed
    z_beta  = norm.ppf(power)

    # Standard formula
    n = (
        (z_alpha * np.sqrt(2 * p1 * (1-p1)) + z_beta * np.sqrt(p1*(1-p1) + p2*(1-p2)))**2
        / (mde_abs**2)
    )
    n_per_variant = int(np.ceil(n))
    n_total       = n_per_variant * n_variants

    # Effect size (Cohen's h)
    h = abs(2 * np.arcsin(np.sqrt(p2)) - 2 * np.arcsin(np.sqrt(p1)))

    return {
        'baseline_rate': baseline_rate,
        'target_rate': round(p2, 6),
        'mde_abs': mde_abs,
        'mde_rel': round(mde_abs / baseline_rate * 100, 2),
        'alpha': alpha, 'power': power, 'n_variants': n_variants,
        'n_per_variant': n_per_variant,
        'n_total': n_total,
        'effect_size_h': round(h, 4),
    }


def compute_duration(
    n_total: int,
    daily_traffic: float,
    traffic_share: float = 1.0,
) -> dict:
    """How many days to collect n_total observations."""
    effective_daily = daily_traffic * traffic_share
    days  = int(np.ceil(n_total / effective_daily)) if effective_daily > 0 else 9999
    weeks = round(days / 7, 1)
    return {
        'daily_eligible': round(effective_daily, 1),
        'days_required': days,
        'weeks_required': weeks,
        'end_date': (pd.Timestamp.today() + pd.Timedelta(days=days)).strftime('%Y-%m-%d'),
    }


# ─────────────────────────────────────────────────────────────────────────────
# OPPORTUNITY SIZING
# ─────────────────────────────────────────────────────────────────────────────
def compute_opportunity(
    monthly_inquiries:   float,
    current_ior:         float,   # current order rate (0–1)
    target_ior:          float,   # target order rate (0–1)
    avg_order_value:     float,   # $ per order
    avg_gross_margin:    float,   # gross margin fraction (0–1)
    time_horizon_months: float = 12,
) -> dict:
    """Revenue opportunity from closing the IOR gap."""
    current_orders  = monthly_inquiries * current_ior
    target_orders   = monthly_inquiries * target_ior
    incremental_orders_mo = target_orders - current_orders
    incremental_rev_mo    = incremental_orders_mo * avg_order_value
    incremental_gm_mo     = incremental_rev_mo * avg_gross_margin

    horizon_orders = incremental_orders_mo * time_horizon_months
    horizon_rev    = incremental_rev_mo    * time_horizon_months
    horizon_gm     = incremental_gm_mo     * time_horizon_months

    return {
        'monthly_inquiries': monthly_inquiries,
        'current_ior': current_ior, 'target_ior': target_ior,
        'ior_gap_pp': round((target_ior - current_ior)*100, 2),
        'current_orders_monthly': round(current_orders, 1),
        'target_orders_monthly':  round(target_orders, 1),
        'incremental_orders_monthly': round(incremental_orders_mo, 1),
        'incremental_revenue_monthly': round(incremental_rev_mo, 0),
        'incremental_gm_monthly': round(incremental_gm_mo, 0),
        f'incremental_orders_{int(time_horizon_months)}mo': round(horizon_orders, 0),
        f'incremental_revenue_{int(time_horizon_months)}mo': round(horizon_rev, 0),
        f'incremental_gm_{int(time_horizon_months)}mo': round(horizon_gm, 0),
        'avg_order_value': avg_order_value,
        'gross_margin': avg_gross_margin,
        'time_horizon_months': time_horizon_months,
    }


print('✅ Statistical utilities loaded')
print('   proportion_test()   — two-proportion z-test with CI + effect size')
print('   means_test()        — Welch t-test with CI + Cohen\'s d')
print('   compute_sample_size() — power-based sample size for proportions')
print('   compute_duration()  — days required given traffic')
print('   compute_opportunity() — revenue opportunity from metric gap')
