from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats
from scipy.special import betaln

logger = logging.getLogger("continum.experimentation.bayesian")


# ─────────────────────────────────────────────────────────────────────────────
# BETA-BINOMIAL (conversion rate experiments)
# ─────────────────────────────────────────────────────────────────────────────

def beta_binomial_test(
    n_ctrl:   int,
    conv_ctrl: int,
    n_treat:  int,
    conv_treat: int,
    prior_alpha: float = 1.0,   # Beta(α, β) prior — (1,1) = uniform
    prior_beta:  float = 1.0,
    alpha: float = 0.05,        # credible interval width (two-sided)
    rope_lo: float = -0.001,    # region of practical equivalence in probability
    rope_hi: float = +0.001,    # e.g. |Δ| < 0.1pp is "practically zero"
    n_samples: int = 50_000,
    seed: int = 42,
) -> Dict:
    rng = np.random.default_rng(seed)

    # Posterior parameters (Beta-Binomial conjugate update)
    alpha_c = prior_alpha + conv_ctrl
    beta_c  = prior_beta  + (n_ctrl  - conv_ctrl)
    alpha_t = prior_alpha + conv_treat
    beta_t  = prior_beta  + (n_treat - conv_treat)

    # Analytic posterior means
    post_mean_ctrl  = alpha_c / (alpha_c + beta_c)
    post_mean_treat = alpha_t / (alpha_t + beta_t)

    # ── P(θ_treat > θ_ctrl) — exact via Gauss-Legendre quadrature ────────────
    p_treat_gt_ctrl = _beta_gt_prob(alpha_t, beta_t, alpha_c, beta_c)

    # ── Monte Carlo for posterior difference Δ = θ_t - θ_c ──────────────────
    theta_ctrl  = rng.beta(alpha_c, beta_c,  size=n_samples)
    theta_treat = rng.beta(alpha_t, beta_t,  size=n_samples)
    delta_samples = theta_treat - theta_ctrl

    # HDI
    credible_interval = _hdi(delta_samples, 1 - alpha)

    # Posterior mean and std of delta
    delta_mean = float(delta_samples.mean())
    delta_std  = float(delta_samples.std())

    # ROPE decision
    prob_rope      = float(np.mean((delta_samples >= rope_lo) & (delta_samples <= rope_hi)))
    prob_practical = float(np.mean(delta_samples > rope_hi))
    prob_harm      = float(np.mean(delta_samples < rope_lo))

    # Expected loss (Bayesian risk)
    loss_ship     = float(np.mean(np.maximum(-delta_samples, 0)))  # loss if ship treatment
    loss_no_ship  = float(np.mean(np.maximum( delta_samples, 0)))  # loss if keep control

    # Bayes factor (H1: θ_t > θ_c vs H0: θ_t = θ_c) via Savage-Dickey
    bayes_factor = _savage_dickey_bf(alpha_t, beta_t, alpha_c, beta_c)

    # Decision rule
    if prob_rope > 0.90:
        decision = "equivalent"
    elif prob_practical > (1 - alpha):
        decision = "ship_treatment"
    elif prob_harm > (1 - alpha):
        decision = "keep_control"
    else:
        decision = "inconclusive"

    logger.debug(
        "BayesianAB: P(T>C)=%.4f  δ_mean=%.4f  BF=%.2f  decision=%s",
        p_treat_gt_ctrl, delta_mean, bayes_factor, decision,
    )

    return {
        "method":             "beta_binomial",
        # Data
        "n_ctrl":             n_ctrl,   "conv_ctrl":   conv_ctrl,
        "n_treat":            n_treat,  "conv_treat":  conv_treat,
        # Posterior parameters
        "posterior_alpha_ctrl":  round(alpha_c, 2),  "posterior_beta_ctrl":  round(beta_c, 2),
        "posterior_alpha_treat": round(alpha_t, 2),  "posterior_beta_treat": round(beta_t, 2),
        # Posterior summaries
        "posterior_mean_ctrl":   round(post_mean_ctrl,  6),
        "posterior_mean_treat":  round(post_mean_treat, 6),
        "delta_posterior_mean":  round(delta_mean, 6),
        "delta_posterior_std":   round(delta_std,  6),
        "delta_posterior_mean_pp": round(delta_mean * 100, 4),
        # Credible interval (HDI)
        "hdi_lo":             round(float(credible_interval[0]), 6),
        "hdi_hi":             round(float(credible_interval[1]), 6),
        "hdi_lo_pp":          round(float(credible_interval[0]) * 100, 4),
        "hdi_hi_pp":          round(float(credible_interval[1]) * 100, 4),
        "hdi_width":          1 - alpha,
        # Probabilistic
        "prob_treat_better":  round(p_treat_gt_ctrl, 6),
        "prob_harm":          round(prob_harm, 6),
        "prob_rope":          round(prob_rope, 6),
        "prob_practical_sig": round(prob_practical, 6),
        # Bayes factor & expected loss
        "bayes_factor":       round(bayes_factor, 4),
        "expected_loss_ship": round(loss_ship, 6),
        "expected_loss_hold": round(loss_no_ship, 6),
        "min_expected_loss":  round(min(loss_ship, loss_no_ship), 6),
        # Decision
        "decision":           decision,
        "rope_lo":            rope_lo,   "rope_hi": rope_hi,
        "alpha":              alpha,
        "prior":              {"alpha": prior_alpha, "beta": prior_beta},
        "n_samples":          n_samples,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NORMAL-NORMAL (continuous / revenue metrics)
# ─────────────────────────────────────────────────────────────────────────────

def normal_normal_test(
    ctrl_vals:  np.ndarray,
    treat_vals: np.ndarray,
    prior_mean: float = 0.0,
    prior_var:  float = 1e6,       # vague (diffuse) prior on mean
    alpha: float = 0.05,
    rope_lo: float = -1.0,         # practical equivalence on raw scale
    rope_hi: float = +1.0,
    n_samples: int = 50_000,
    seed: int = 42,
) -> Dict:
    rng = np.random.default_rng(seed)
    ctrl  = np.asarray(ctrl_vals[~np.isnan(ctrl_vals)],   dtype=float)
    treat = np.asarray(treat_vals[~np.isnan(treat_vals)],  dtype=float)

    n_c, n_t   = len(ctrl), len(treat)
    xbar_c, xbar_t = float(ctrl.mean()), float(treat.mean())
    s2_c = float(np.var(ctrl, ddof=1))
    s2_t = float(np.var(treat, ddof=1))

    # Posterior mean and variance
    def _post(xbar, s2, n):
        prec_prior = 1 / prior_var
        prec_lik   = n / s2 if s2 > 0 else 1e9
        prec_post  = prec_prior + prec_lik
        mu_post    = (prior_mean * prec_prior + xbar * prec_lik) / prec_post
        var_post   = 1 / prec_post
        return mu_post, var_post

    mu_c_post, var_c_post = _post(xbar_c, s2_c, n_c)
    mu_t_post, var_t_post = _post(xbar_t, s2_t, n_t)

    # Posterior of difference
    delta_post_mean = mu_t_post - mu_c_post
    delta_post_var  = var_c_post + var_t_post
    delta_post_std  = float(np.sqrt(delta_post_var))

    # Monte Carlo samples
    samples_c = rng.normal(mu_c_post, np.sqrt(var_c_post), size=n_samples)
    samples_t = rng.normal(mu_t_post, np.sqrt(var_t_post), size=n_samples)
    delta_samples = samples_t - samples_c

    prob_treat_better = float(np.mean(delta_samples > 0))
    credible_interval = _hdi(delta_samples, 1 - alpha)

    prob_rope      = float(np.mean((delta_samples >= rope_lo) & (delta_samples <= rope_hi)))
    prob_practical = float(np.mean(delta_samples > rope_hi))
    prob_harm      = float(np.mean(delta_samples < rope_lo))

    if prob_rope > 0.90:
        decision = "equivalent"
    elif prob_practical > (1 - alpha):
        decision = "ship_treatment"
    elif prob_harm > (1 - alpha):
        decision = "keep_control"
    else:
        decision = "inconclusive"

    return {
        "method":             "normal_normal",
        "n_ctrl":             n_c,     "n_treat":      n_t,
        "mean_ctrl":          round(xbar_c, 4),
        "mean_treat":         round(xbar_t, 4),
        "delta_posterior_mean": round(delta_post_mean, 4),
        "delta_posterior_std":  round(delta_post_std,  4),
        "hdi_lo":             round(float(credible_interval[0]), 4),
        "hdi_hi":             round(float(credible_interval[1]), 4),
        "prob_treat_better":  round(prob_treat_better, 4),
        "prob_harm":          round(prob_harm, 4),
        "prob_rope":          round(prob_rope, 4),
        "prob_practical_sig": round(prob_practical, 4),
        "decision":           decision,
        "rope_lo":            rope_lo, "rope_hi": rope_hi,
        "alpha":              alpha,
        "n_samples":          n_samples,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-ARM BAYESIAN (pick the best variant)
# ─────────────────────────────────────────────────────────────────────────────

def bayesian_multi_arm(
    arm_data: Dict[str, Tuple[int, int]],   # {"variant": (n_obs, n_conversions)}
    prior_alpha: float = 1.0,
    prior_beta:  float = 1.0,
    n_samples:   int   = 100_000,
    seed: int = 42,
) -> Dict:
    rng    = np.random.default_rng(seed)
    arms   = list(arm_data.keys())
    n_arms = len(arms)

    samples = np.empty((n_samples, n_arms))
    post_params = {}
    for i, arm in enumerate(arms):
        n, c = arm_data[arm]
        a = prior_alpha + c
        b = prior_beta  + (n - c)
        post_params[arm] = (a, b)
        samples[:, i] = rng.beta(a, b, size=n_samples)

    # P(arm i is best) = fraction of samples where arm i has the highest rate
    best_counts = np.argmax(samples, axis=1)
    prob_best   = {arm: float(np.mean(best_counts == i)) for i, arm in enumerate(arms)}

    # Expected loss for each arm (opportunity cost of choosing it)
    # loss_i = E[max_j(θ_j) - θ_i | θ_i is chosen]
    max_per_sample = samples.max(axis=1)
    expected_loss  = {
        arm: float(np.mean(max_per_sample - samples[:, i]))
        for i, arm in enumerate(arms)
    }
    post_means = {arm: p[0] / (p[0] + p[1]) for arm, p in post_params.items()}

    # Rank arms by posterior mean
    ranked = sorted(arms, key=lambda a: post_means[a], reverse=True)
    recommended = ranked[0]

    return {
        "method":           "bayesian_multi_arm",
        "arms":             arms,
        "n_samples":        n_samples,
        "posterior_means":  {a: round(v, 6) for a, v in post_means.items()},
        "prob_best":        {a: round(v, 4) for a, v in prob_best.items()},
        "expected_loss":    {a: round(v, 6) for a, v in expected_loss.items()},
        "ranked_arms":      ranked,
        "recommended_arm":  recommended,
    }


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _beta_gt_prob(alpha1: float, beta1: float,
                  alpha2: float, beta2: float) -> float:
    # Use numeric integration (more general than the sum formula)
    from scipy.integrate import quad

    def integrand(x):
        # P(B2 < x) * f_B1(x)
        log_f1 = ((alpha1 - 1) * np.log(max(x, 1e-300))
                  + (beta1 - 1) * np.log(max(1 - x, 1e-300))
                  - betaln(alpha1, beta1))
        cdf2   = float(stats.beta.cdf(x, alpha2, beta2))
        return np.exp(log_f1) * cdf2

    result, _ = quad(integrand, 0, 1, limit=200)
    return float(np.clip(result, 0, 1))


def _hdi(samples: np.ndarray, credible_mass: float = 0.95) -> Tuple[float, float]:
    sorted_samples = np.sort(samples)
    n = len(sorted_samples)
    interval_idx   = int(np.floor(credible_mass * n))
    n_intervals    = n - interval_idx
    if n_intervals <= 0:
        return (float(sorted_samples[0]), float(sorted_samples[-1]))
    widths = sorted_samples[interval_idx:] - sorted_samples[:n_intervals]
    min_idx = int(np.argmin(widths))
    return (float(sorted_samples[min_idx]),
            float(sorted_samples[min_idx + interval_idx]))


def _savage_dickey_bf(alpha_t: float, beta_t: float,
                      alpha_c: float, beta_c: float) -> float:
    try:
        # Under H0: both arms have the same rate θ drawn from Beta
        # Marginal likelihood ratio (simplified approximation)
        post_at_zero_t = float(stats.beta.pdf(0.5, alpha_t, beta_t))
        post_at_zero_c = float(stats.beta.pdf(0.5, alpha_c, beta_c))
        prior_at_zero  = float(stats.beta.pdf(0.5, 1.0, 1.0))  # uniform prior
        if prior_at_zero == 0:
            return 1.0
        bf = (post_at_zero_t * post_at_zero_c) / (prior_at_zero ** 2)
        return float(np.clip(bf, 0.001, 1000))
    except Exception:
        return 1.0


__all__ = [
    "beta_binomial_test",
    "normal_normal_test",
    "bayesian_multi_arm",
]
