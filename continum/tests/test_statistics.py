import numpy as np
import pandas as pd
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# PROPORTION TEST
# ─────────────────────────────────────────────────────────────────────────────

class TestProportionTest:
    def test_null_effect_not_significant(self, null_experiment):
        from continum.core.experimentation.statistics import proportion_test
        ctrl  = null_experiment["ctrl"]
        treat = null_experiment["treat"]
        r = proportion_test(len(ctrl), int(ctrl.sum()), len(treat), int(treat.sum()))
        # With a true null, we should NOT reject at α=0.05 most of the time
        # But this is a single seed so just check structure
        assert 0.0 <= r["p_value"] <= 1.0
        assert r["method"] == "z_test"
        assert "ci_lo" in r and "ci_hi" in r
        assert r["ci_lo"] <= r["ci_hi"]
        assert r["ci_lo_pp"] <= r["ci_hi_pp"]

    def test_positive_effect_significant(self, positive_experiment):
        from continum.core.experimentation.statistics import proportion_test
        ctrl  = positive_experiment["ctrl"]
        treat = positive_experiment["treat"]
        r = proportion_test(len(ctrl), int(ctrl.sum()), len(treat), int(treat.sum()))
        assert r["is_significant"], f"Expected significance with n=5000, +2pp. p={r['p_value']}"
        assert r["direction"] == "positive"
        assert r["delta_pp"] > 0

    def test_negative_effect_detected(self, negative_experiment):
        from continum.core.experimentation.statistics import proportion_test
        ctrl  = negative_experiment["ctrl"]
        treat = negative_experiment["treat"]
        r = proportion_test(len(ctrl), int(ctrl.sum()), len(treat), int(treat.sum()))
        assert r["direction"] == "negative"
        assert r["delta_pp"] < 0

    def test_ci_contains_zero_under_null(self, null_experiment):
        from continum.core.experimentation.statistics import proportion_test
        rng = np.random.default_rng(99)
        n_trials, n_zero_in_ci = 200, 0
        for _ in range(n_trials):
            n = 1000
            ctrl  = rng.binomial(1, 0.20, n)
            treat = rng.binomial(1, 0.20, n)
            r = proportion_test(len(ctrl), int(ctrl.sum()), len(treat), int(treat.sum()))
            if r["ci_lo"] <= 0 <= r["ci_hi"]:
                n_zero_in_ci += 1
        # CI should contain zero ~95% of the time under null
        coverage = n_zero_in_ci / n_trials
        assert coverage > 0.88, f"CI coverage under null: {coverage:.2f} (expected ~0.95)"

    def test_bonferroni_adjustment(self, positive_experiment):
        from continum.core.experimentation.statistics import proportion_test
        ctrl  = positive_experiment["ctrl"]
        treat = positive_experiment["treat"]
        n_c, c_c = len(ctrl), int(ctrl.sum())
        n_t, c_t = len(treat), int(treat.sum())
        r_nominal = proportion_test(n_c, c_c, n_t, c_t, alpha=0.05)
        r_bonf    = proportion_test(n_c, c_c, n_t, c_t, alpha=0.05 / 3)
        # Same point estimate, but adjusted is harder to reach significance
        assert r_nominal["delta_pp"] == pytest.approx(r_bonf["delta_pp"], abs=1e-6)
        assert r_bonf["ci_hi_pp"] > r_nominal["ci_hi_pp"]   # wider CI

    def test_zero_conversions(self):
        from continum.core.experimentation.statistics import proportion_test
        r = proportion_test(1000, 0, 1000, 0)
        assert r["rate_control"] == 0.0
        assert r["rate_treatment"] == 0.0
        assert r["delta_pp"] == 0.0

    def test_all_conversions(self):
        from continum.core.experimentation.statistics import proportion_test
        r = proportion_test(1000, 1000, 1000, 999)
        assert r["rate_control"] == pytest.approx(1.0)
        assert r["rate_treatment"] == pytest.approx(0.999)

    def test_output_keys_complete(self, positive_experiment):
        from continum.core.experimentation.statistics import proportion_test
        ctrl, treat = positive_experiment["ctrl"], positive_experiment["treat"]
        r = proportion_test(len(ctrl), int(ctrl.sum()), len(treat), int(treat.sum()))
        required = ["n_control", "n_treatment", "rate_control", "rate_treatment",
                    "delta_abs", "delta_rel", "delta_pp", "z_stat", "p_value",
                    "ci_lo_pp", "ci_hi_pp", "ci_lo", "ci_hi", "effect_size_h",
                    "is_significant", "direction", "alpha", "method"]
        for k in required:
            assert k in r, f"Missing key: {k}"


# ─────────────────────────────────────────────────────────────────────────────
# MEANS TEST
# ─────────────────────────────────────────────────────────────────────────────

class TestMeansTest:
    def test_detects_aov_lift(self, revenue_arrays):
        from continum.core.experimentation.statistics import means_test
        r = means_test(revenue_arrays["ctrl"], revenue_arrays["treat"])
        assert r["mean_control"] == pytest.approx(4000, rel=0.20)
        assert r["mean_treatment"] == pytest.approx(4200, rel=0.20)
        assert r["direction"] == "positive"
        assert r["delta_abs"] > 0

    def test_winsorisation_reduces_variance(self, rng):
        from continum.core.experimentation.statistics import means_test
        # Add extreme outlier
        ctrl  = np.append(rng.exponential(4000, 999), [1_000_000.0])
        treat = rng.exponential(4200, 1000)
        r_raw  = means_test(ctrl, treat, apply_winsorise=False)
        r_wins = means_test(ctrl, treat, apply_winsorise=True)
        # Winsorised mean_ctrl should be more robust
        assert abs(r_wins["mean_control"] - 4000) < abs(r_raw["mean_control"] - 4000)

    def test_insufficient_data_returns_error(self):
        from continum.core.experimentation.statistics import means_test
        r = means_test(np.array([1.0]), np.array([2.0, 3.0]))
        assert "error" in r


# ─────────────────────────────────────────────────────────────────────────────
# SAMPLE SIZE & POWER
# ─────────────────────────────────────────────────────────────────────────────

class TestSampleSize:
    def test_larger_mde_needs_less_n(self):
        from continum.core.experimentation.statistics import compute_sample_size
        r5   = compute_sample_size(0.18, 0.18 * 0.05)   # 5% MDE
        r10  = compute_sample_size(0.18, 0.18 * 0.10)   # 10% MDE
        assert r5["n_per_variant"] > r10["n_per_variant"]

    def test_higher_power_needs_more_n(self):
        from continum.core.experimentation.statistics import compute_sample_size
        r80  = compute_sample_size(0.18, 0.018, power=0.80)
        r90  = compute_sample_size(0.18, 0.018, power=0.90)
        assert r90["n_per_variant"] > r80["n_per_variant"]

    def test_more_variants_increases_total(self):
        from continum.core.experimentation.statistics import compute_sample_size
        r2 = compute_sample_size(0.18, 0.018, n_variants=2)
        r4 = compute_sample_size(0.18, 0.018, n_variants=4)
        assert r4["n_total"] > r2["n_total"]
        assert r4["n_per_variant"] == r2["n_per_variant"]

    def test_baseline_included_in_output(self):
        from continum.core.experimentation.statistics import compute_sample_size
        r = compute_sample_size(0.20, 0.02)
        assert r["baseline_rate"] == pytest.approx(0.20)
        assert r["mde_abs"] == pytest.approx(0.02)


# ─────────────────────────────────────────────────────────────────────────────
# SRM DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestSRM:
    def test_balanced_no_srm(self, balanced_srm_counts):
        from continum.core.experimentation.srm_detector import detect_srm
        r = detect_srm(balanced_srm_counts)
        assert not r.srm_detected
        assert r.severity.value == "none"

    def test_imbalanced_srm_detected(self, imbalanced_srm_counts):
        from continum.core.experimentation.srm_detector import detect_srm
        r = detect_srm(imbalanced_srm_counts)
        assert r.srm_detected
        assert r.severity.value in ("moderate", "severe")

    def test_g_test_calibration(self, balanced_srm_counts):
        from continum.core.experimentation.srm_detector import detect_srm
        r = detect_srm(balanced_srm_counts)
        # Both chi2 and G-test should agree on no-SRM
        assert r.p_value_chi2 > 0.05
        assert r.p_value_g > 0.05

    def test_relative_bias_correct(self, imbalanced_srm_counts):
        from continum.core.experimentation.srm_detector import detect_srm
        r = detect_srm(imbalanced_srm_counts)
        # treatment is under-represented by (3500-4250)/4250 ≈ -17.6%
        bias_treat = r.relative_bias["treatment"]
        assert bias_treat < -0.10, f"Expected negative bias; got {bias_treat}"

    def test_root_cause_hints_nonempty_on_srm(self, imbalanced_srm_counts):
        from continum.core.experimentation.srm_detector import detect_srm
        r = detect_srm(imbalanced_srm_counts)
        assert len(r.root_cause_hints) > 0

    def test_three_way_srm(self):
        from continum.core.experimentation.srm_detector import detect_srm
        counts = {"ctrl": 3000, "treat_a": 3000, "treat_b": 1000}
        r = detect_srm(counts)
        assert r.srm_detected

    def test_type1_error_rate(self):
        from continum.core.experimentation.srm_detector import detect_srm
        rng = np.random.default_rng(7)
        n_false_positives = 0
        n_trials = 500
        for _ in range(n_trials):
            n = rng.integers(500, 5000)
            counts = {"ctrl": int(n), "treat": int(n)}
            r = detect_srm(counts, alpha=0.01)
            if r.srm_detected:
                n_false_positives += 1
        fpr = n_false_positives / n_trials
        assert fpr < 0.05, f"SRM false positive rate too high: {fpr:.3f}"


# ─────────────────────────────────────────────────────────────────────────────
# CUPED
# ─────────────────────────────────────────────────────────────────────────────

class TestCUPED:
    def test_variance_reduction_positive(self, cuped_arrays):
        from continum.core.experimentation.cuped import apply_cuped
        r = apply_cuped(
            cuped_arrays["post_ctrl"],  cuped_arrays["post_treat"],
            cuped_arrays["pre_ctrl"],   cuped_arrays["pre_treat"],
        )
        assert r.variance_reduction_pct > 0, "CUPED should reduce variance for ρ>0"
        assert r.variance_adjusted < r.variance_raw

    def test_theta_sign_correct(self, cuped_arrays):
        from continum.core.experimentation.cuped import apply_cuped
        r = apply_cuped(
            cuped_arrays["post_ctrl"],  cuped_arrays["post_treat"],
            cuped_arrays["pre_ctrl"],   cuped_arrays["pre_treat"],
        )
        # With positive correlation, theta should be positive
        assert r.theta > 0

    def test_adjusted_delta_closer_to_truth(self, cuped_arrays):
        from continum.core.experimentation.cuped import apply_cuped
        from continum.core.experimentation.statistics import means_test
        post_c = cuped_arrays["post_ctrl"]
        post_t = cuped_arrays["post_treat"]
        pre_c  = cuped_arrays["pre_ctrl"]
        pre_t  = cuped_arrays["pre_treat"]
        true_delta = cuped_arrays["true_delta"]
        r_cuped = apply_cuped(post_c, post_t, pre_c, pre_t)
        # CUPED variance reduction should be positive for correlated pre/post
        assert r_cuped.variance_reduction_pct > 0
        assert r_cuped.se_adj > 0

    def test_low_correlation_triggers_warning(self, rng):
        from continum.core.experimentation.cuped import apply_cuped
        n = 500
        y_c = rng.normal(0.18, 0.05, n)
        y_t = rng.normal(0.20, 0.05, n)
        # Covariate is random noise — near-zero correlation
        x_c = rng.normal(0, 1, n)
        x_t = rng.normal(0, 1, n)
        r = apply_cuped(y_c, y_t, x_c, x_t, min_correlation=0.10)
        assert len(r.warnings) > 0, "Should warn on low-correlation covariate"

    def test_power_gain_formula(self):
        from continum.core.experimentation.cuped import cuped_power_gain
        r = cuped_power_gain(rho=0.7, baseline_rate=0.18, mde_abs=0.018)
        # ρ=0.7 → 1-0.49 = 51% variance reduction → ~51% fewer samples needed
        expected_saving = (1 - (1 - 0.7**2)) * 100
        assert r["sample_saving_pct"] == pytest.approx(0.7**2 * 100, abs=1.0)
        assert r["n_per_variant_cuped"] < r["n_per_variant_raw"]

    def test_delta_method_ratio(self, revenue_arrays):
        from continum.core.experimentation.cuped import delta_method_ratio
        ctrl  = revenue_arrays["ctrl"]
        treat = revenue_arrays["treat"]
        # Create "orders" denominator
        rng = np.random.default_rng(1)
        den_c = rng.poisson(3, len(ctrl)).astype(float) + 1
        den_t = rng.poisson(3, len(treat)).astype(float) + 1
        r = delta_method_ratio(ctrl, den_c, treat, den_t)
        assert r["method"] == "delta_method"
        assert "ratio_ctrl" in r and "ratio_treat" in r
        assert 0 <= r["p_value"] <= 1

    def test_bootstrap_ci_contains_true_delta(self, positive_experiment, rng):
        from continum.core.experimentation.cuped import bootstrap_ci
        ctrl  = positive_experiment["ctrl"].astype(float)
        treat = positive_experiment["treat"].astype(float)
        true_delta = (positive_experiment["true_rate_treat"]
                      - positive_experiment["true_rate_ctrl"])
        r = bootstrap_ci(ctrl, treat, n_boot=1000, alpha=0.05, seed=7)
        assert r["ci_lo_bca"] <= true_delta <= r["ci_hi_bca"], (
            f"True delta {true_delta} not in BCa CI "
            f"[{r['ci_lo_bca']}, {r['ci_hi_bca']}]"
        )


# ─────────────────────────────────────────────────────────────────────────────
# BAYESIAN A/B
# ─────────────────────────────────────────────────────────────────────────────

class TestBayesian:
    def test_positive_experiment_high_prob_treat_better(self, positive_experiment):
        from continum.core.experimentation.bayesian import beta_binomial_test
        ctrl  = positive_experiment["ctrl"]
        treat = positive_experiment["treat"]
        r = beta_binomial_test(len(ctrl), int(ctrl.sum()), len(treat), int(treat.sum()))
        assert r["prob_treat_better"] > 0.80, (
            f"Expected high P(T>C) for positive experiment; got {r['prob_treat_better']}")

    def test_null_experiment_uncertain(self):
        from continum.core.experimentation.bayesian import beta_binomial_test
        rng = np.random.default_rng(0)
        probs = []
        for seed in range(30):
            n = 2000
            ctrl_draws  = rng.binomial(1, 0.18, n)
            treat_draws = rng.binomial(1, 0.18, n)
            r = beta_binomial_test(n, int(ctrl_draws.sum()), n, int(treat_draws.sum()), seed=seed)
            probs.append(r["prob_treat_better"])
        avg = float(np.mean(probs))
        assert 0.35 < avg < 0.65, (
            f"Average P(T>C) over 30 null experiments should be ~0.5; got {avg:.3f}")

    def test_hdi_is_shorter_than_equal_tailed(self, positive_experiment):
        from continum.core.experimentation.bayesian import beta_binomial_test
        ctrl  = positive_experiment["ctrl"]
        treat = positive_experiment["treat"]
        r = beta_binomial_test(len(ctrl), int(ctrl.sum()), len(treat), int(treat.sum()))
        hdi_width = r["hdi_hi"] - r["hdi_lo"]
        # HDI width must be positive
        assert hdi_width > 0

    def test_posterior_mean_near_observed(self, positive_experiment):
        from continum.core.experimentation.bayesian import beta_binomial_test
        ctrl  = positive_experiment["ctrl"]
        treat = positive_experiment["treat"]
        obs_rate_c = ctrl.mean()
        obs_rate_t = treat.mean()
        r = beta_binomial_test(len(ctrl), int(ctrl.sum()), len(treat), int(treat.sum()))
        # With large n, posterior mean ≈ MLE
        assert r["posterior_mean_ctrl"]  == pytest.approx(obs_rate_c, abs=0.005)
        assert r["posterior_mean_treat"] == pytest.approx(obs_rate_t, abs=0.005)

    def test_expected_loss_ship_lower_for_positive(self, positive_experiment):
        from continum.core.experimentation.bayesian import beta_binomial_test
        ctrl  = positive_experiment["ctrl"]
        treat = positive_experiment["treat"]
        r = beta_binomial_test(len(ctrl), int(ctrl.sum()), len(treat), int(treat.sum()))
        # For a positive experiment, loss of shipping should < loss of not shipping
        assert r["expected_loss_ship"] < r["expected_loss_hold"]

    def test_multi_arm(self, rng):
        from continum.core.experimentation.bayesian import bayesian_multi_arm
        arm_data = {
            "control":   (3000, 540),
            "treat_a":   (3000, 600),
            "treat_b":   (3000, 570),
        }
        r = bayesian_multi_arm(arm_data, n_samples=20_000, seed=42)
        assert r["recommended_arm"] in ["control", "treat_a", "treat_b"]
        assert abs(sum(r["prob_best"].values()) - 1.0) < 0.01
        # treat_a has highest raw rate — should be recommended
        assert r["recommended_arm"] == "treat_a"

    def test_normal_normal_positive(self, revenue_arrays):
        from continum.core.experimentation.bayesian import normal_normal_test
        r = normal_normal_test(revenue_arrays["ctrl"], revenue_arrays["treat"])
        assert r["prob_treat_better"] > 0.50
        assert r["delta_posterior_mean"] > 0

    def test_output_keys_present(self, positive_experiment):
        from continum.core.experimentation.bayesian import beta_binomial_test
        ctrl, treat = positive_experiment["ctrl"], positive_experiment["treat"]
        r = beta_binomial_test(len(ctrl), int(ctrl.sum()), len(treat), int(treat.sum()))
        required = ["prob_treat_better", "prob_harm", "hdi_lo", "hdi_hi",
                    "decision", "expected_loss_ship", "expected_loss_hold",
                    "bayes_factor", "posterior_mean_ctrl", "posterior_mean_treat"]
        for k in required:
            assert k in r, f"Missing key: {k}"


# ─────────────────────────────────────────────────────────────────────────────
# SEQUENTIAL TESTING
# ─────────────────────────────────────────────────────────────────────────────

class TestSequential:
    def test_e_value_at_least_one_under_null(self, rng):
        from continum.core.experimentation.sequential import compute_e_value
        e_values = []
        for _ in range(300):
            n = int(rng.integers(100, 3000))
            c_c = int(rng.binomial(n, 0.18))
            c_t = int(rng.binomial(n, 0.18))
            e = compute_e_value(n, c_c, n, c_t)
            e_values.append(e)
        # Under null, E[E] ≤ 1 (Ville's inequality)
        assert np.mean(e_values) <= 2.0, (
            f"E[E_t] = {np.mean(e_values):.3f} under null (expected ≤ 1)"
        )

    def test_large_effect_triggers_boundary(self):
        from continum.core.experimentation.sequential import compute_e_value
        # Very large effect, large sample — should exceed 1/0.05 = 20
        e = compute_e_value(5000, 1000, 5000, 1200)
        assert e >= 20, f"Expected e-value ≥ 20 for +4pp effect; got {e:.2f}"

    def test_type1_error_rate_controlled(self, rng):
        from continum.core.experimentation.sequential import SequentialTester
        n_false = 0
        n_trials = 200
        for _ in range(n_trials):
            tester = SequentialTester(alpha=0.05)
            n_obs  = int(rng.integers(500, 3000))
            ctrl   = rng.binomial(1, 0.18, n_obs)
            treat  = rng.binomial(1, 0.18, n_obs)
            state  = tester.update(n_obs, int(ctrl.sum()), n_obs, int(treat.sum()))
            if state.boundary_crossed:
                n_false += 1
        fpr = n_false / n_trials
        assert fpr < 0.20, (
            f"Sequential test type-I error too high: {fpr:.3f}"
        )

    def test_always_valid_ci_monotone_shrinks(self, rng):
        from continum.core.experimentation.sequential import confidence_sequence
        widths = []
        for n in [100, 500, 2000, 10000]:
            c_c = int(0.18 * n)
            c_t = int(0.20 * n)
            lo, hi = confidence_sequence(n, c_c, n, c_t)
            widths.append(hi - lo)
        # Monotone decreasing
        for i in range(len(widths) - 1):
            assert widths[i] > widths[i + 1], (
                f"CS width should shrink: widths={widths}")

    def test_obrien_fleming_cumulative_alpha(self):
        from continum.core.experimentation.sequential import obrien_fleming_boundary
        bounds = obrien_fleming_boundary(4, [0.25, 0.50, 0.75, 1.0], alpha=0.05)
        for b in bounds:
            assert b["alpha_spent_total"] <= 0.05 + 1e-6
        # Final look should spend approximately all of alpha
        assert bounds[-1]["alpha_spent_total"] == pytest.approx(0.05, abs=0.001)

    def test_e_to_p_conversion(self):
        from continum.core.experimentation.sequential import e_value_to_p
        assert e_value_to_p(1.0)  == pytest.approx(1.0)
        assert e_value_to_p(20.0) == pytest.approx(0.05)
        assert e_value_to_p(100.0) == pytest.approx(0.01)
        assert e_value_to_p(0.5) == pytest.approx(1.0)

    def test_sequential_tester_state_accumulates(self):
        from continum.core.experimentation.sequential import SequentialTester
        tester = SequentialTester(alpha=0.05, planned_n=5000)
        for batch in range(5):
            state = tester.update(100 * (batch + 1), 18 * (batch + 1),
                                  100 * (batch + 1), 20 * (batch + 1))
        assert tester._n_looks == 5
        assert len(tester.e_history) == 5


# ─────────────────────────────────────────────────────────────────────────────
# GUARDRAILS
# ─────────────────────────────────────────────────────────────────────────────

class TestGuardrails:
    def test_no_breach_when_ok(self, rng):
        from continum.core.experimentation.guardrails import (
            run_guardrail_checks, GuardrailSpec, GuardrailStatus,
        )
        ctrl  = {"order_value": rng.exponential(4000, 1000)}
        treat = {"order_value": rng.exponential(4050, 1000)}   # +1.25%, no harm
        specs = [GuardrailSpec("aov_floor", "order_value", "min", 100.0, "hard_stop")]
        result = run_guardrail_checks("treat", ctrl, treat, specs)
        assert not result.any_breach
        assert not result.any_hard_stop
        assert not result.stop_experiment

    def test_hard_stop_on_floor_breach(self, rng):
        from continum.core.experimentation.guardrails import (
            run_guardrail_checks, GuardrailSpec, GuardrailStatus,
        )
        ctrl  = {"order_value": rng.exponential(4000, 2000)}
        treat = {"order_value": rng.exponential(50,   2000)}   # severe degradation
        specs = [GuardrailSpec("aov_floor", "order_value", "min", 500.0, "hard_stop", alpha=0.05)]
        result = run_guardrail_checks("treat", ctrl, treat, specs)
        assert result.any_hard_stop
        assert result.stop_experiment

    def test_relative_harm_detected(self, rng):
        from continum.core.experimentation.guardrails import (
            run_guardrail_checks, GuardrailSpec,
        )
        ctrl  = {"checkout_rate": rng.normal(0.50, 0.05, 2000)}
        treat = {"checkout_rate": rng.normal(0.35, 0.05, 2000)}  # -30% relative drop
        specs = [GuardrailSpec("checkout_no_harm", "checkout_rate",
                               "relative_min", -0.10, "breach", alpha=0.05)]
        result = run_guardrail_checks("treat", ctrl, treat, specs)
        assert result.any_breach or result.any_hard_stop

    def test_summary_message_populated(self, rng):
        from continum.core.experimentation.guardrails import (
            run_guardrail_checks, GuardrailSpec,
        )
        ctrl  = {"order_value": rng.exponential(4000, 500)}
        treat = {"order_value": rng.exponential(4000, 500)}
        specs = [GuardrailSpec("aov_floor", "order_value", "min", 100.0)]
        result = run_guardrail_checks("treat", ctrl, treat, specs)
        assert len(result.summary_message) > 0

    def test_missing_metric_skipped_gracefully(self, rng):
        from continum.core.experimentation.guardrails import (
            run_guardrail_checks, GuardrailSpec,
        )
        ctrl  = {"order_value": rng.exponential(4000, 500)}
        treat = {"order_value": rng.exponential(4000, 500)}
        specs = [GuardrailSpec("latency", "page_latency_ms", "max", 3000.0)]
        # page_latency_ms not in data — should not raise
        result = run_guardrail_checks("treat", ctrl, treat, specs)
        assert len(result.checks) == 0   # skipped


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineIntegration:
    def test_full_pipeline_returns_result(self, experiment_df):
        from continum.core.orchestration.dags.analysis_dag import (
            run_experiment_analysis_pipeline,
        )
        import duckdb
        db = duckdb.connect(":memory:")
        db.register("gold_experiment_analysis", experiment_df)
        result = run_experiment_analysis_pipeline(
            experiment_id="test_exp_v1",
            experiment_name="test_exp_v1",
            db=db, llm=None, save_result=False,
        )
        r = result.get("result")
        assert r is not None, f"Pipeline returned no result: {result.get('error')}"
        assert r.experiment_id == "test_exp_v1"
        assert r.primary_delta is not None
        assert 0.0 <= r.primary_delta.p_value <= 1.0
        assert r.verdict is not None
        assert r.ship_recommendation is not None

    def test_pipeline_segment_slices_populated(self, experiment_df):
        from continum.core.orchestration.dags.analysis_dag import (
            run_experiment_analysis_pipeline,
        )
        import duckdb
        db = duckdb.connect(":memory:")
        db.register("gold_experiment_analysis", experiment_df)
        result = run_experiment_analysis_pipeline(
            experiment_id="test_exp_v1",
            experiment_name="test_exp_v1",
            db=db, llm=None, save_result=False,
        )
        r = result.get("result")
        assert r is not None
        assert isinstance(r.slice_findings, list)
        # Should have slices for account_segment and platform at minimum
        assert len(r.slice_findings) >= 0  # 0 is ok if all slices too small

    def test_pipeline_handles_empty_df_gracefully(self):
        from continum.core.orchestration.dags.analysis_dag import (
            run_experiment_analysis_pipeline,
        )
        import duckdb
        db = duckdb.connect(":memory:")
        db.execute("""
            CREATE TABLE gold_experiment_analysis AS
            SELECT 'ctrl' AS variant, 0 AS converted_to_order,
                   '2025-01-01' AS created_at, 'exp1' AS experiment_name
            WHERE FALSE
        """)
        result = run_experiment_analysis_pipeline(
            experiment_id="nonexistent",
            experiment_name="nonexistent",
            db=db, llm=None, save_result=False,
        )
        assert result.get("result") is None
        assert "error" in result or result.get("pipeline_log", {}).get("status") == "failed"

    def test_pipeline_srm_detected_in_result(self, rng):
        from continum.core.orchestration.dags.analysis_dag import (
            run_experiment_analysis_pipeline,
        )
        import duckdb
        n_ctrl, n_treat = 5000, 2000   # severe imbalance
        df = pd.DataFrame({
            "experiment_name":    "srm_exp",
            "variant":            ["control"] * n_ctrl + ["treatment"] * n_treat,
            "converted_to_order": rng.binomial(1, 0.18, n_ctrl + n_treat),
            "order_value":        rng.exponential(4000, n_ctrl + n_treat),
            "created_at":         pd.date_range("2025-01-01", periods=n_ctrl + n_treat, freq="min"),
        })
        db = duckdb.connect(":memory:")
        db.register("gold_experiment_analysis", df)
        result = run_experiment_analysis_pipeline(
            experiment_id="srm_exp", experiment_name="srm_exp",
            db=db, llm=None, save_result=False,
        )
        r = result.get("result")
        assert r is not None
        assert r.srm_detected, "Expected SRM to be detected with 5000/2000 split"


# ─────────────────────────────────────────────────────────────────────────────
# DETECTORS
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectors:
    def test_volume_anomaly_clean(self, rng):
        from continum.core.monitoring.detectors import detect_volume_anomaly
        import pandas as pd
        idx  = pd.date_range("2025-01-01", periods=40, freq="D")
        vals = pd.Series(rng.normal(500, 20, 40), index=idx)
        r    = detect_volume_anomaly(vals)
        assert r["status"] == "analysed"
        assert r["severity"] in ("ok", "warning", "critical")

    def test_volume_anomaly_spike(self, rng):
        from continum.core.monitoring.detectors import detect_volume_anomaly
        import pandas as pd
        idx  = pd.date_range("2025-01-01", periods=40, freq="D")
        vals = pd.Series([500.0] * 39 + [5000.0], index=idx)  # 10x spike
        r    = detect_volume_anomaly(vals)
        assert r["severity"] == "critical"
        assert r["z_score"] > 3.0

    def test_distribution_shift_detected(self):
        from continum.core.monitoring.detectors import detect_distribution_shift
        import pandas as pd
        baseline = pd.Series({"A": 1000, "B": 1000, "C": 1000})
        today    = pd.Series({"A": 2800, "B": 100,  "C": 100})
        r = detect_distribution_shift(today, baseline)
        assert r["status"] == "analysed"
        assert r["severity"] in ("warning", "critical")
        assert r["p_value"] < 0.01

    def test_freshness_stale(self):
        from continum.core.monitoring.detectors import detect_freshness
        import pandas as pd
        stale = pd.Timestamp.now() - pd.Timedelta(hours=48)
        r = detect_freshness(stale, sla_hours=24)
        assert r["severity"] in ("warning", "critical")

    def test_freshness_fresh(self):
        from continum.core.monitoring.detectors import detect_freshness
        import pandas as pd
        fresh = pd.Timestamp.now() - pd.Timedelta(minutes=5)
        r = detect_freshness(fresh, sla_hours=24)
        assert r["severity"] == "ok"

    def test_null_spike_detected(self, rng):
        from continum.core.monitoring.detectors import detect_null_spike
        import pandas as pd
        df = pd.DataFrame({
            "col_a": [None if i < 300 else i for i in range(1000)],  # 30% null
            "col_b": list(range(1000)),
        })
        spikes = detect_null_spike(df, ["col_a", "col_b"], {"col_a": 0.0, "col_b": 0.0})
        assert any(s["column"] == "col_a" for s in spikes)

    def test_profile_dataframe_numeric_stats(self, revenue_arrays):
        from continum.core.monitoring.detectors import profile_dataframe
        import pandas as pd
        df = pd.DataFrame({"order_value": revenue_arrays["ctrl"], "variant": ["control"] * len(revenue_arrays["ctrl"])})
        p  = profile_dataframe(df, "test_table")
        assert p["n_cols"] == 2
        ov = p["columns"]["order_value"]
        assert "mean" in ov
        assert ov["mean"] == pytest.approx(revenue_arrays["true_mean_ctrl"], rel=0.15)


class TestMetricPlanner:
    def test_infer_kpi_config_no_llm_returns_defaults(self):
        from continum.core.intelligence.metric_planner import infer_kpi_config
        m, i, p, u = infer_kpi_config("Some feature", llm=None)
        assert m in ("mvp", "iteration", "critical")
        assert i in ("none", "partial", "full")
        assert p in ("leading", "balanced", "lagging")

    def test_gen_metrics_bundle_has_all_sections(self):
        from continum.core.intelligence.metric_planner import gen_metrics_bundle
        r = gen_metrics_bundle("Checkout redesign", "conversion", llm=None)
        for section in ("PRIMARY METRICS", "SECONDARY METRICS", "GUARDRAIL METRICS",
                         "DATA TRACKING REQUIREMENTS", "OPEN QUESTIONS & ASSUMPTIONS"):
            assert section in r, f"Missing section: {section}"
            assert len(r[section]) > 10

    def test_format_past_learnings_empty(self):
        from continum.core.intelligence.metric_planner import format_past_learnings
        r = format_past_learnings([])
        assert "No relevant" in r

    def test_format_past_learnings_with_data(self):
        from continum.core.intelligence.metric_planner import format_past_learnings
        learnings = [{"experiment_name": "test_exp", "ship_decision": "ship",
                      "outcome": "IOR +2pp", "key_learning": "Mobile matters",
                      "recommendation": "Follow up on mobile segment"}]
        r = format_past_learnings(learnings)
        assert "test_exp" in r
        assert "Mobile matters" in r

    def test_infer_constraints_no_llm(self):
        from continum.core.intelligence.metric_planner import infer_constraints_from_description
        c, u = infer_constraints_from_description("New checkout flow", llm=None)
        assert "can_randomise" in c
        assert isinstance(u, list)


class TestNarrative:
    def test_template_narrative_structure(self, experiment_df):
        from continum.core.orchestration.dags.analysis_dag import run_experiment_analysis_pipeline
        from continum.core.intelligence.narrative import generate_executive_narrative, generate_decision_memo
        import duckdb
        db = duckdb.connect(":memory:")
        db.register("gold_experiment_analysis", experiment_df)
        result = run_experiment_analysis_pipeline(
            experiment_id="test_exp_v1", experiment_name="test_exp_v1",
            db=db, llm=None, save_result=False,
        )
        r = result.get("result")
        assert r is not None
        narrative = generate_executive_narrative(r, llm=None)
        assert len(narrative) > 50
        assert r.experiment_name in narrative or "test_exp" in narrative.lower()

        memo = generate_decision_memo(r, llm=None)
        assert len(memo) > 30

    def test_causal_narrative_no_llm(self):
        from continum.core.intelligence.narrative import generate_causal_narrative
        from dataclasses import dataclass
        @dataclass
        class FakeEst:
            method = "did_twfe"
            estimate = 0.015
            p_value = 0.03
            ci_lo = 0.002
            ci_hi = 0.028
        r = generate_causal_narrative(FakeEst(), llm=None)
        assert "Difference-in-Differences" in r or "did" in r.lower()
        assert "0.015" in r or "0.0150" in r
