"""
Statistical calibration checks for continum/ExpSuite/stats_inference.

A test that always returns a plausible-looking p-value is not the same as a
test that is *correctly calibrated*: under the null hypothesis (no real
effect), a test run at alpha=0.05 must flag "significant" on roughly 5% of
trials, not some other rate. These run many simulated A/A trials and check
the long-run false-positive rate against the nominal alpha, rather than
asserting on any single draw.

Marked slow (excluded from the default `-m "not slow"` run) because each test
runs thousands of simulated trials.
"""

import numpy as np
import pytest
from continum.ExpSuite.stats_inference.srm_detector import SRMInput, detect_srm
from continum.ExpSuite.stats_inference.statistics import StatTestInput, calculate_hypothesis_test

N_TRIALS = 2000


@pytest.mark.slow
def test_hypothesis_test_false_positive_rate_matches_alpha_under_the_null():
    rng = np.random.default_rng(1234)
    alpha = 0.05
    n_per_group = 200
    false_positives = 0

    for _ in range(N_TRIALS):
        # Both groups drawn from the identical distribution: any "significant"
        # result here is by definition a false positive.
        control = rng.normal(loc=100.0, scale=20.0, size=n_per_group)
        treatment = rng.normal(loc=100.0, scale=20.0, size=n_per_group)

        result = calculate_hypothesis_test(
            StatTestInput(
                control_mean=float(control.mean()),
                control_std=float(control.std(ddof=1)),
                control_count=n_per_group,
                treatment_mean=float(treatment.mean()),
                treatment_std=float(treatment.std(ddof=1)),
                treatment_count=n_per_group,
                alpha=alpha,
            )
        )
        if result.is_stat_sig:
            false_positives += 1

    observed_rate = false_positives / N_TRIALS
    # Binomial std error at p=0.05, n=2000 is ~0.0049; allow a wide +/-3x band
    # so the test is robust to RNG/platform drift while still catching a
    # miscalibrated test (e.g. one that fires 20%+ of the time).
    assert (
        0.02 <= observed_rate <= 0.09
    ), f"expected ~{alpha:.0%} false positives under the null, got {observed_rate:.2%}"


@pytest.mark.slow
def test_srm_detector_false_positive_rate_matches_alpha_under_balanced_traffic():
    rng = np.random.default_rng(5678)
    alpha = 0.01
    total_per_trial = 4000
    false_positives = 0

    for _ in range(N_TRIALS):
        # A truly 50/50 random split — any "SRM detected" here is a false
        # positive, not a real mismatch.
        control_count = int(rng.binomial(total_per_trial, 0.5))
        treatment_count = total_per_trial - control_count

        result = detect_srm(SRMInput(observed_counts=[control_count, treatment_count], alpha=alpha))
        if result.has_srm:
            false_positives += 1

    observed_rate = false_positives / N_TRIALS
    # Binomial std error at p=0.01, n=2000 is ~0.0022; allow a wide band.
    assert (
        0.002 <= observed_rate <= 0.025
    ), f"expected ~{alpha:.0%} false positives under balanced traffic, got {observed_rate:.2%}"
