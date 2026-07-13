from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

# ── Simulation parameters ────────────────────────────────────────────────────
N_SIMS_FAST = 200  # for tests where each iteration is cheap
N_SIMS_MEDIUM = 500  # for calibration curves
N_SIMS_SLOW = 1000  # for fine-grained type-I error estimates

ALPHA = 0.05
POWER_TARGET = 0.80
TOLERANCE_PP = 0.06  # ±6pp tolerance on rates (generous for Monte Carlo)


# ─────────────────────────────────────────────────────────────────────────────
# TYPE-I ERROR RATE
# ─────────────────────────────────────────────────────────────────────────────


class TestTypeIError:

    def test_proportion_test_type1_nominal_n(self):
        from continum.experimentation.stats.statistics import proportion_test

        rng = np.random.default_rng(0)
        rejections = 0
        for _ in range(N_SIMS_SLOW):
            ctrl = rng.binomial(500, 0.18)
            treat = rng.binomial(500, 0.18)
            r = proportion_test(500, ctrl, 500, treat, alpha=ALPHA)
            if r["is_significant"]:
                rejections += 1
        fpr = rejections / N_SIMS_SLOW
        assert (
            abs(fpr - ALPHA) < TOLERANCE_PP
        ), f"Type-I error = {fpr:.3f}, expected ~{ALPHA} ±{TOLERANCE_PP}"

    def test_proportion_test_type1_small_n(self):
        from continum.experimentation.stats.statistics import proportion_test

        rng = np.random.default_rng(1)
        rejections = sum(
            1
            for _ in range(N_SIMS_SLOW)
            if proportion_test(100, rng.binomial(100, 0.18), 100, rng.binomial(100, 0.18))[
                "is_significant"
            ]
        )
        fpr = rejections / N_SIMS_SLOW
        assert fpr <= ALPHA + 0.04, f"Type-I error too high at small n: {fpr:.3f}"

    def test_means_test_type1(self):
        from continum.experimentation.stats.statistics import means_test

        rng = np.random.default_rng(2)
        rejections = sum(
            1
            for _ in range(N_SIMS_FAST)
            if means_test(rng.exponential(4000, 500), rng.exponential(4000, 500))["is_significant"]
        )
        fpr = rejections / N_SIMS_FAST
        assert abs(fpr - ALPHA) < TOLERANCE_PP + 0.02, f"Means test FPR = {fpr:.3f}"

    def test_bonferroni_correction_reduces_fpr(self):
        from continum.experimentation.stats.statistics import proportion_test

        rng = np.random.default_rng(3)
        rej_nom, rej_bonf = 0, 0
        alpha_bonf = ALPHA / 3
        for _ in range(N_SIMS_FAST):
            n, c_c = 500, rng.binomial(500, 0.18)
            c_t = rng.binomial(500, 0.18)
            if proportion_test(n, c_c, n, c_t, ALPHA)["is_significant"]:
                rej_nom += 1
            if proportion_test(n, c_c, n, c_t, alpha_bonf)["is_significant"]:
                rej_bonf += 1
        assert rej_bonf <= rej_nom, "Bonferroni should not increase rejections"
        assert rej_bonf / N_SIMS_FAST <= ALPHA / 3 + TOLERANCE_PP


# ─────────────────────────────────────────────────────────────────────────────
# STATISTICAL POWER
# ─────────────────────────────────────────────────────────────────────────────


class TestPower:

    def test_power_at_designed_n(self):
        from continum.experimentation.stats.statistics import (
            compute_sample_size,
            proportion_test,
        )

        baseline = 0.18
        mde_abs = 0.018  # 10% relative
        ss = compute_sample_size(baseline, mde_abs, ALPHA, POWER_TARGET, n_variants=2)
        n = ss["n_per_variant"]
        rng = np.random.default_rng(10)
        detections = sum(
            1
            for _ in range(N_SIMS_FAST)
            if proportion_test(
                n, rng.binomial(n, baseline), n, rng.binomial(n, baseline + mde_abs)
            )["is_significant"]
        )
        empirical_power = detections / N_SIMS_FAST
        assert (
            empirical_power >= POWER_TARGET - 0.07
        ), f"Empirical power = {empirical_power:.3f}, expected ≥ {POWER_TARGET - 0.07}"

    def test_larger_effect_has_higher_power(self):
        from continum.experimentation.stats.statistics import proportion_test

        rng = np.random.default_rng(11)
        n = 2000

        def _emp_power(mde):
            return (
                sum(
                    1
                    for _ in range(N_SIMS_FAST)
                    if proportion_test(n, rng.binomial(n, 0.18), n, rng.binomial(n, 0.18 + mde))[
                        "is_significant"
                    ]
                )
                / N_SIMS_FAST
            )

        p_small = _emp_power(0.005)
        p_large = _emp_power(0.030)
        assert (
            p_large > p_small
        ), f"Larger effect should have more power: {p_large:.3f} vs {p_small:.3f}"

    def test_more_n_monotonically_increases_power(self):
        from continum.experimentation.stats.statistics import proportion_test

        rng = np.random.default_rng(12)
        powers = []
        for n in [100, 300, 1000, 3000]:
            det = sum(
                1
                for _ in range(N_SIMS_FAST)
                if proportion_test(n, rng.binomial(n, 0.18), n, rng.binomial(n, 0.20))[
                    "is_significant"
                ]
            )
            powers.append(det / N_SIMS_FAST)
        for i in range(len(powers) - 1):
            assert (
                powers[i] <= powers[i + 1] + 0.05
            ), f"Power not monotone: n=100..3000 → {[round(p,3) for p in powers]}"


# ─────────────────────────────────────────────────────────────────────────────
# CUPED CALIBRATION
# ─────────────────────────────────────────────────────────────────────────────


class TestCupedCalibration:

    def _gen_correlated(self, rng, n, rho, true_delta=0.0):
        pre_c = rng.normal(0.18, 0.05, n)
        pre_t = rng.normal(0.18, 0.05, n)
        eps_c = rng.normal(0, np.sqrt(1 - rho**2) * 0.05, n)
        eps_t = rng.normal(0, np.sqrt(1 - rho**2) * 0.05, n)
        post_c = np.clip(rho * pre_c + eps_c, 0.001, 0.999)
        post_t = np.clip(rho * pre_t + eps_t + true_delta, 0.001, 0.999)
        return pre_c, pre_t, post_c, post_t

    def test_variance_reduction_matches_rho_squared(self):
        from continum.experimentation.stats.cuped import apply_cuped

        rng = np.random.default_rng(20)
        rho = 0.70
        expected = rho**2 * 100  # ~49%
        reductions = []
        for _ in range(50):
            pre_c, pre_t, post_c, post_t = self._gen_correlated(rng, 1000, rho)
            r = apply_cuped(post_c, post_t, pre_c, pre_t)
            reductions.append(r.variance_reduction_pct)
        avg_reduction = float(np.mean(reductions))
        assert (
            abs(avg_reduction - expected) < 15
        ), f"CUPED variance reduction = {avg_reduction:.1f}%, expected ~{expected:.1f}%"

    def test_cuped_type1_error_not_inflated(self):
        from continum.experimentation.stats.cuped import apply_cuped

        rng = np.random.default_rng(21)
        rejections = 0
        for _ in range(N_SIMS_FAST):
            pre_c, pre_t, post_c, post_t = self._gen_correlated(rng, 500, 0.60)
            r = apply_cuped(post_c, post_t, pre_c, pre_t, alpha=ALPHA)
            if r.is_significant:
                rejections += 1
        fpr = rejections / N_SIMS_FAST
        assert (
            fpr <= ALPHA + TOLERANCE_PP
        ), f"CUPED type-I error = {fpr:.3f}, expected ≤ {ALPHA + TOLERANCE_PP}"

    def test_cuped_point_estimate_unbiased(self):
        from continum.experimentation.stats.cuped import apply_cuped

        rng = np.random.default_rng(22)
        deltas = []
        for _ in range(N_SIMS_FAST):
            pre_c, pre_t, post_c, post_t = self._gen_correlated(rng, 500, 0.60)
            r = apply_cuped(post_c, post_t, pre_c, pre_t)
            deltas.append(r.delta_adj)
        avg_delta = float(np.mean(deltas))
        assert abs(avg_delta) < 0.005, f"CUPED estimator biased: mean δ = {avg_delta:.5f}"

    def test_no_variance_reduction_without_covariate(self):
        from continum.experimentation.stats.cuped import apply_cuped

        rng = np.random.default_rng(23)
        reductions = []
        for _ in range(30):
            y_c = rng.normal(0.18, 0.05, 500)
            y_t = rng.normal(0.18, 0.05, 500)
            x_c = rng.uniform(0, 1, 500)  # purely random covariate
            x_t = rng.uniform(0, 1, 500)
            r = apply_cuped(y_c, y_t, x_c, x_t)
            reductions.append(r.variance_reduction_pct)
        avg = float(np.mean(reductions))
        assert avg < 10, f"Random covariate should not reduce variance: mean={avg:.1f}%"


# ─────────────────────────────────────────────────────────────────────────────
# BAYESIAN CALIBRATION
# ─────────────────────────────────────────────────────────────────────────────


class TestBayesianCalibration:

    def test_prob_treat_better_calibrated_under_null(self):
        from continum.experimentation.stats.bayesian import beta_binomial_test

        rng = np.random.default_rng(30)
        probs = []
        for s in range(N_SIMS_MEDIUM):
            n, c_c = 1000, rng.binomial(1000, 0.18)
            c_t = rng.binomial(1000, 0.18)
            r = beta_binomial_test(n, c_c, n, c_t, seed=s)
            probs.append(r["prob_treat_better"])
        avg = float(np.mean(probs))
        assert abs(avg - 0.50) < 0.04, f"Mean P(T>C) under null = {avg:.4f}, expected 0.50 ±0.04"

    def test_prob_treat_better_high_for_large_effect(self):
        from continum.experimentation.stats.bayesian import beta_binomial_test

        rng = np.random.default_rng(31)
        probs = []
        for s in range(100):
            n, c_c = 5000, rng.binomial(5000, 0.18)
            c_t = rng.binomial(5000, 0.23)  # +5pp true effect
            r = beta_binomial_test(n, c_c, n, c_t, seed=s)
            probs.append(r["prob_treat_better"])
        avg = float(np.mean(probs))
        assert avg > 0.90, f"Mean P(T>C) for +5pp effect = {avg:.4f}, expected > 0.90"

    def test_hdi_coverage(self):
        from continum.experimentation.stats.bayesian import beta_binomial_test

        rng = np.random.default_rng(32)
        true_delta = 0.02
        coverage_count = 0
        for s in range(N_SIMS_FAST):
            n = 1000
            c_c = rng.binomial(n, 0.18)
            c_t = rng.binomial(n, 0.18 + true_delta)
            r = beta_binomial_test(n, c_c, n, c_t, seed=s, alpha=0.05)
            if r["hdi_lo"] <= true_delta <= r["hdi_hi"]:
                coverage_count += 1
        coverage = coverage_count / N_SIMS_FAST
        assert coverage >= 0.85, f"HDI 95% coverage = {coverage:.3f}, expected ≥ 0.85"

    def test_expected_loss_ordering_correct(self):
        from continum.experimentation.stats.bayesian import beta_binomial_test

        # Positive
        r_pos = beta_binomial_test(5000, 1000, 5000, 1150, seed=1)  # +3pp
        assert r_pos["expected_loss_ship"] < r_pos["expected_loss_hold"]
        # Negative
        r_neg = beta_binomial_test(5000, 1000, 5000, 850, seed=2)  # -3pp
        assert r_neg["expected_loss_ship"] > r_neg["expected_loss_hold"]


# ─────────────────────────────────────────────────────────────────────────────
# SEQUENTIAL TESTING CALIBRATION
# ─────────────────────────────────────────────────────────────────────────────


class TestSequentialCalibration:

    def test_msprt_type1_error_at_final_look(self):
        from continum.experimentation.stats.sequential import compute_e_value, e_value_to_p

        rng = np.random.default_rng(40)
        rej = 0
        threshold = 1.0 / ALPHA
        for _ in range(N_SIMS_SLOW):
            n, c_c = 1000, rng.binomial(1000, 0.18)
            c_t = rng.binomial(1000, 0.18)
            e = compute_e_value(n, c_c, n, c_t)
            if e >= threshold:
                rej += 1
        fpr = rej / N_SIMS_SLOW
        assert (
            fpr <= ALPHA + TOLERANCE_PP
        ), f"mSPRT type-I error = {fpr:.3f}, expected ≤ {ALPHA + TOLERANCE_PP}"

    def test_msprt_valid_under_repeated_peeking(self):
        from continum.experimentation.stats.sequential import SequentialTester

        rng = np.random.default_rng(41)
        threshold = 1.0 / ALPHA  # noqa: F841
        ever_rejected = 0
        n_per_look = 100
        n_looks = 10
        for _ in range(N_SIMS_MEDIUM):
            tester = SequentialTester(alpha=ALPHA)
            data_c = rng.binomial(1, 0.18, n_per_look * n_looks)
            data_t = rng.binomial(1, 0.18, n_per_look * n_looks)
            rejected = False
            for look in range(n_looks):
                sl = slice(0, (look + 1) * n_per_look)
                state = tester.update(
                    (look + 1) * n_per_look,
                    int(data_c[sl].sum()),
                    (look + 1) * n_per_look,
                    int(data_t[sl].sum()),
                )
                if state.boundary_crossed:
                    rejected = True
                    break
            if rejected:
                ever_rejected += 1
        fpr = ever_rejected / N_SIMS_MEDIUM
        assert fpr <= ALPHA + TOLERANCE_PP, (
            f"Sequential peeking type-I error = {fpr:.3f}, " f"expected ≤ {ALPHA + TOLERANCE_PP}"
        )

    def test_confidence_sequence_valid_simultaneously(self):
        from continum.experimentation.stats.sequential import confidence_sequence

        rng = np.random.default_rng(42)
        true_d = 0.0  # null
        ns = [200, 500, 1000, 2000]
        for n in ns:
            coverage = 0
            for s in range(N_SIMS_FAST):
                c_c = rng.binomial(n, 0.18)
                c_t = rng.binomial(n, 0.18)
                lo, hi = confidence_sequence(n, c_c, n, c_t, alpha=ALPHA)
                if lo <= true_d <= hi:
                    coverage += 1
            emp_coverage = coverage / N_SIMS_FAST
            assert emp_coverage >= 1 - ALPHA - TOLERANCE_PP, (
                f"CS coverage at n={n}: {emp_coverage:.3f}, "
                f"expected ≥ {1 - ALPHA - TOLERANCE_PP:.3f}"
            )

    def test_obrien_fleming_alpha_spending_monotone(self):
        from continum.experimentation.stats.sequential import obrien_fleming_boundary

        fracs = [0.20, 0.40, 0.60, 0.80, 1.00]
        bounds = obrien_fleming_boundary(5, fracs, alpha=ALPHA)
        spends = [b["alpha_spent_total"] for b in bounds]
        for i in range(len(spends) - 1):
            assert spends[i] <= spends[i + 1], f"OBF alpha not monotone: {spends}"


# ─────────────────────────────────────────────────────────────────────────────
# BOOTSTRAP CI COVERAGE
# ─────────────────────────────────────────────────────────────────────────────


class TestBootstrapCoverage:

    def test_bca_ci_contains_true_delta(self):
        from continum.experimentation.stats.cuped import bootstrap_ci

        rng = np.random.default_rng(50)
        true_d = 200.0  # treatment has AOV 4200 vs 4000
        coverage = 0
        for seed in range(N_SIMS_FAST):
            ctrl = rng.exponential(4000, 300)
            treat = rng.exponential(4200, 300)
            r = bootstrap_ci(ctrl, treat, n_boot=500, alpha=ALPHA, seed=seed)
            if r["ci_lo_bca"] <= true_d <= r["ci_hi_bca"]:
                coverage += 1
        emp = coverage / N_SIMS_FAST
        assert emp >= 0.85, f"BCa coverage = {emp:.3f}, expected ≥ 0.85"

    def test_bootstrap_ci_for_proportion(self):
        from continum.experimentation.stats.cuped import bootstrap_ci

        rng = np.random.default_rng(51)
        true_d = 0.02  # +2pp
        coverage = 0
        for seed in range(N_SIMS_FAST):
            ctrl = rng.binomial(1, 0.18, 400).astype(float)
            treat = rng.binomial(1, 0.20, 400).astype(float)
            r = bootstrap_ci(ctrl, treat, n_boot=500, alpha=ALPHA, seed=seed)
            if r["ci_lo_bca"] <= true_d <= r["ci_hi_bca"]:
                coverage += 1
        emp = coverage / N_SIMS_FAST
        assert emp >= 0.80, f"BCa proportion CI coverage = {emp:.3f}"


# ─────────────────────────────────────────────────────────────────────────────
# NUMERICAL STABILITY
# ─────────────────────────────────────────────────────────────────────────────


class TestNumericalStability:

    def test_proportion_test_zero_conversions(self):
        from continum.experimentation.stats.statistics import proportion_test

        r = proportion_test(1000, 0, 1000, 0)
        assert r["p_value"] == 1.0
        assert not np.isnan(r["z_stat"])

    def test_proportion_test_all_conversions(self):
        from continum.experimentation.stats.statistics import proportion_test

        r = proportion_test(1000, 1000, 1000, 999)
        assert not np.isnan(r["p_value"])
        assert not np.isinf(r["z_stat"])

    def test_proportion_test_single_observation(self):
        from continum.experimentation.stats.statistics import proportion_test

        r = proportion_test(1, 0, 1, 1)
        assert 0 <= r["p_value"] <= 1

    def test_means_test_identical_arrays(self):
        from continum.experimentation.stats.statistics import means_test

        arr = np.full(100, 4000.0)
        r = means_test(arr, arr)
        assert "error" in r or r["p_value"] == 1.0

    def test_means_test_single_value_arrays(self):
        from continum.experimentation.stats.statistics import means_test

        r = means_test(np.array([1.0]), np.array([2.0]))
        assert "error" in r  # not enough data

    def test_cuped_extreme_correlation(self):
        from continum.experimentation.stats.cuped import apply_cuped

        rng = np.random.default_rng(60)
        n = 300
        pre_c = rng.normal(0.18, 0.05, n)
        pre_t = rng.normal(0.18, 0.05, n)
        # near-perfect correlation
        post_c = pre_c + rng.normal(0, 0.001, n)
        post_t = pre_t + rng.normal(0, 0.001, n) + 0.02
        r = apply_cuped(pre_c, pre_t, post_c, post_t)
        assert not np.isnan(r.delta_adj)
        assert not np.isinf(r.delta_adj)
        assert r.variance_adjusted >= 0

    def test_cuped_zero_variance_covariate(self):
        from continum.experimentation.stats.cuped import apply_cuped

        rng = np.random.default_rng(61)
        y_c = rng.normal(0.18, 0.05, 200)
        y_t = rng.normal(0.20, 0.05, 200)
        x_c = np.ones(200)  # constant — zero variance
        x_t = np.ones(200)
        r = apply_cuped(y_c, y_t, x_c, x_t)
        assert not np.isnan(r.delta_adj)
        assert r.theta == pytest.approx(0.0, abs=1e-6)

    def test_srm_single_variant(self):
        from continum.experimentation.stats.srm_detector import detect_srm

        r = detect_srm({"control": 5000})
        # df=0, undefined but must not raise
        assert r is not None

    def test_srm_zero_observations(self):
        from continum.experimentation.stats.srm_detector import detect_srm

        r = detect_srm({"control": 0, "treatment": 0})
        assert not r.srm_detected

    def test_bayesian_zero_conversions(self):
        from continum.experimentation.stats.bayesian import beta_binomial_test

        r = beta_binomial_test(1000, 0, 1000, 0)
        assert 0 <= r["prob_treat_better"] <= 1
        assert not np.isnan(r["delta_posterior_mean"])

    def test_bayesian_extreme_conversions(self):
        from continum.experimentation.stats.bayesian import beta_binomial_test

        r = beta_binomial_test(1000, 1000, 1000, 999)
        assert 0 <= r["prob_treat_better"] <= 1

    def test_bootstrap_single_unique_value(self):
        from continum.experimentation.stats.cuped import bootstrap_ci

        ctrl = np.ones(100)  # all same value
        treat = np.ones(100) * 1.1
        r = bootstrap_ci(ctrl, treat, n_boot=100, seed=1)
        assert 0 <= r["p_value"] <= 1
        assert not np.isnan(r["observed"])

    def test_sequential_empty_arms(self):
        from continum.experimentation.stats.sequential import compute_e_value

        e = compute_e_value(0, 0, 0, 0)
        assert e == 1.0  # no information = no evidence

    def test_delta_method_zero_denominator(self):
        from continum.experimentation.stats.cuped import delta_method_ratio

        rng = np.random.default_rng(62)
        num_c = rng.exponential(100, 200)
        num_t = rng.exponential(110, 200)
        den_c = np.ones(200) * 0.0001  # near-zero denominator
        den_t = np.ones(200) * 0.0001
        r = delta_method_ratio(num_c, den_c, num_t, den_t)
        assert not np.isnan(r["ratio_ctrl"])

    def test_profile_dataframe_all_null_column(self):
        import pandas as pd

        from continum.experimentation.monitoring.detectors import profile_dataframe

        df = pd.DataFrame(
            {
                "all_null": [None] * 100,
                "normal": list(range(100)),
            }
        )
        p = profile_dataframe(df)
        assert p["columns"]["all_null"]["null_rate"] == pytest.approx(1.0)

    def test_detect_volume_anomaly_constant_series(self):
        import pandas as pd

        from continum.experimentation.monitoring.detectors import detect_volume_anomaly

        idx = pd.date_range("2025-01-01", periods=40, freq="D")
        vals = pd.Series([500.0] * 40, index=idx)
        r = detect_volume_anomaly(vals)
        assert r["status"] in ("analysed", "insufficient_data")
        assert r.get("z_score") is not None or r["status"] == "insufficient_data"


# ─────────────────────────────────────────────────────────────────────────────
# SRM CALIBRATION
# ─────────────────────────────────────────────────────────────────────────────


class TestSRMCalibration:

    def test_srm_false_positive_rate_at_alpha_001(self):
        rng = np.random.default_rng(70)
        from continum.experimentation.stats.srm_detector import detect_srm

        fp = 0
        for _ in range(N_SIMS_SLOW):
            n = int(rng.integers(500, 5000))
            counts = {"control": n, "treatment": n}
            if detect_srm(counts, alpha=0.01).srm_detected:
                fp += 1
        fpr = fp / N_SIMS_SLOW
        assert fpr <= 0.02, f"SRM FPR at α=0.01: {fpr:.4f} (expected ≤ 0.02)"

    def test_srm_power_high_for_large_imbalance(self):
        from continum.experimentation.stats.srm_detector import detect_srm

        detections = sum(
            1
            for _ in range(N_SIMS_FAST)
            if detect_srm({"control": 5000, "treatment": 4000}, alpha=0.01).srm_detected
        )
        power = detections / N_SIMS_FAST
        assert power > 0.95, f"SRM detection rate for 20% imbalance = {power:.3f}"

    def test_srm_severity_correlates_with_imbalance(self):
        from continum.experimentation.stats.srm_detector import SRMSeverity, detect_srm

        mild_imbalance = detect_srm({"control": 1000, "treatment": 950}, alpha=0.01)
        severe_imbalance = detect_srm({"control": 1000, "treatment": 500}, alpha=0.01)
        severity_rank = {"none": 0, "mild": 1, "moderate": 2, "severe": 3}
        assert (
            severity_rank[severe_imbalance.severity.value]
            >= severity_rank[mild_imbalance.severity.value]
        )
