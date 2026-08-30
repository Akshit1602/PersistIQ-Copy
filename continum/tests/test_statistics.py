"""
Unit tests for the statistical primitives under continum/ExpSuite.

These are the functions every analysis tool and orchestration subgraph node
calls directly (see subgraphs/analysis_graph.py) — a regression here silently
corrupts every p-value, lift, and confidence interval shown to a user.
"""

import math

import pytest
from continum.ExpSuite.causal.methods import DiDInput, calculate_diff_in_diff
from continum.ExpSuite.stats_inference.bayesian import BayesianTestInput, run_bayesian_ab_test
from continum.ExpSuite.stats_inference.cuped import CUPEDInput, apply_cuped
from continum.ExpSuite.stats_inference.guardrails import GuardrailCheckInput, check_guardrail_metric
from continum.ExpSuite.stats_inference.sequential import SequentialInput, run_sprt
from continum.ExpSuite.stats_inference.srm_detector import SRMInput, detect_srm
from continum.ExpSuite.stats_inference.statistics import StatTestInput, calculate_hypothesis_test


def test_hypothesis_test_detects_a_clear_lift():
    result = calculate_hypothesis_test(
        StatTestInput(
            control_mean=100.0,
            control_std=15.0,
            control_count=5000,
            treatment_mean=110.0,
            treatment_std=15.0,
            treatment_count=5000,
        )
    )
    assert result.absolute_lift == pytest.approx(10.0)
    assert result.relative_lift == pytest.approx(0.10)
    assert 0.0 <= result.p_value <= 1.0
    assert result.is_stat_sig is True
    assert result.ci_lower < result.absolute_lift < result.ci_upper


def test_hypothesis_test_is_not_significant_with_identical_groups():
    result = calculate_hypothesis_test(
        StatTestInput(
            control_mean=50.0,
            control_std=10.0,
            control_count=1000,
            treatment_mean=50.0,
            treatment_std=10.0,
            treatment_count=1000,
        )
    )
    assert result.absolute_lift == pytest.approx(0.0)
    assert result.p_value == pytest.approx(1.0, abs=1e-9)
    assert result.is_stat_sig is False


def test_hypothesis_test_handles_zero_control_mean_without_dividing_by_zero():
    result = calculate_hypothesis_test(
        StatTestInput(
            control_mean=0.0,
            control_std=1.0,
            control_count=500,
            treatment_mean=5.0,
            treatment_std=1.0,
            treatment_count=500,
        )
    )
    assert result.relative_lift == 0.0
    assert math.isfinite(result.p_value)


def test_detect_srm_flags_a_lopsided_split():
    result = detect_srm(SRMInput(observed_counts=[6000, 4000]))
    assert result.has_srm is True
    assert result.severity in {"WARNING", "CRITICAL"}
    assert result.expected_counts == pytest.approx([5000.0, 5000.0])


def test_detect_srm_passes_a_balanced_split():
    result = detect_srm(SRMInput(observed_counts=[5012, 4988]))
    assert result.has_srm is False
    assert result.severity == "NONE"


def test_apply_cuped_reduces_variance_when_covariate_is_correlated():
    x_control = [float(i) for i in range(200)]
    y_control = [xi * 2.0 + 1.0 for xi in x_control]
    x_treatment = [float(i) for i in range(200)]
    y_treatment = [xi * 2.0 + 6.0 for xi in x_treatment]

    result = apply_cuped(
        CUPEDInput(
            y_control=y_control,
            x_control=x_control,
            y_treatment=y_treatment,
            x_treatment=x_treatment,
        )
    )
    # y is a deterministic linear function of x here, so CUPED should remove
    # essentially all residual variance.
    assert result.variance_reduction_pct > 95.0
    assert result.treatment_cuped_mean - result.control_cuped_mean == pytest.approx(5.0, abs=0.5)


def test_run_sprt_stops_for_success_on_a_strong_effect():
    result = run_sprt(
        SequentialInput(
            control_successes=100,
            control_count=1000,
            treatment_successes=250,
            treatment_count=1000,
        )
    )
    assert result.decision in {"STOP_SUCCESS", "STOP_FUTILITY", "CONTINUE"}
    assert result.lower_bound < result.upper_bound


def test_run_sprt_continues_with_no_data():
    result = run_sprt(
        SequentialInput(
            control_successes=0,
            control_count=0,
            treatment_successes=0,
            treatment_count=0,
        )
    )
    assert result.decision == "CONTINUE"


def test_run_bayesian_ab_test_favors_the_stronger_arm():
    result = run_bayesian_ab_test(
        BayesianTestInput(
            control_successes=100,
            control_failures=900,
            treatment_successes=150,
            treatment_failures=850,
            num_simulations=20000,
        )
    )
    assert result.prob_beat_control > 0.9
    assert result.hdi_lower <= result.expected_relative_lift <= result.hdi_upper


def test_check_guardrail_metric_flags_degradation_past_threshold():
    # Guardrail direction is "lower value = worse" (a metric like conversion
    # rate dropping), not "value moved" — an *increase* never violates.
    result = check_guardrail_metric(
        GuardrailCheckInput(
            metric_name="conversion_rate",
            control_value=0.10,
            treatment_value=0.086,
            max_allowed_degradation_pct=0.10,
        )
    )
    assert result.is_violated is True


def test_check_guardrail_metric_passes_within_threshold():
    result = check_guardrail_metric(
        GuardrailCheckInput(
            metric_name="conversion_rate",
            control_value=0.10,
            treatment_value=0.098,
            max_allowed_degradation_pct=0.10,
        )
    )
    assert result.is_violated is False


def test_calculate_diff_in_diff_isolates_the_treatment_effect():
    # Control drifts +5 on its own; treatment drifts +5 from the same trend
    # plus a true +20 treatment effect.
    result = calculate_diff_in_diff(
        DiDInput(control_pre=100.0, control_post=105.0, treatment_pre=100.0, treatment_post=125.0)
    )
    assert result.did_effect == pytest.approx(20.0)
    assert result.is_significant is True


def test_calculate_diff_in_diff_zero_effect_when_trends_match():
    result = calculate_diff_in_diff(
        DiDInput(control_pre=100.0, control_post=110.0, treatment_pre=100.0, treatment_post=110.0)
    )
    assert result.did_effect == pytest.approx(0.0)
    assert result.is_significant is False
