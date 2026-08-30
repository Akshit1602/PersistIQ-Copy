"""Baselines must be derived from the sample datasets, not asserted.

Every check here pins a value to the aggregation that produced it, so a
regression that silently reintroduces a hardcoded constant fails.
"""

import pytest
from continum.mapMeta.baseline_profiler import (
    BaselineProfile,
    get_baseline_profile,
    profile_from_sample_data,
    profile_from_warehouse,
    resolve_dataset,
)

DIGITAL = resolve_dataset("digital")
STORE = resolve_dataset("store")

requires_digital = pytest.mark.skipif(DIGITAL is None, reason="Xometry sample data not present")
requires_store = pytest.mark.skipif(STORE is None, reason="Shell sample data not present")


@requires_digital
def test_digital_profile_derives_conversion_and_order_value():
    profile = profile_from_sample_data(DIGITAL, "digital", "Unmatched Experiment Name")

    ior = profile.fields["baselineIor"]
    assert 0 < ior.value < 1
    assert ior.row_count > 1000
    assert "quotes" in ior.rationale

    # currentIor mirrors baselineIor so opportunity sizing and power calculator
    # never disagree about the same underlying rate.
    assert profile.fields["currentIor"].value == ior.value

    assert profile.fields["aov"].value > 0
    assert profile.fields["dailyTraffic"].value > 0
    assert profile.fields["monthlyInquiries"].value > profile.fields["dailyTraffic"].value


@requires_digital
def test_digital_profile_prefers_the_matching_experiment_log():
    matched = profile_from_sample_data(DIGITAL, "digital", "Mobile Nav Redesign")

    assert matched.experiment_match == "mobile_nav_redesign"
    assert matched.fields["variants"].value >= 2
    assert "mobile_nav_redesign" in matched.fields["baselineIor"].source

    # An experiment with no assignment log falls back to the account-wide rate.
    fallback = profile_from_sample_data(DIGITAL, "digital", "Totally Unknown Test")
    assert fallback.experiment_match is None
    assert fallback.fields["baselineIor"].source == "quotes.csv"


@requires_digital
def test_digital_profile_omits_gross_margin():
    # The order tables carry no cost basis — a margin here would be a benchmark
    # wearing a data badge.
    profile = profile_from_sample_data(DIGITAL, "digital", "Mobile Nav Redesign")
    assert "grossMargin" not in profile.fields


@requires_store
def test_store_profile_dedupes_the_product_grain():
    profile = profile_from_sample_data(STORE, "store", "Dedicated Cashier Staffing Rollout")

    assert profile.fields["targetStoreCount"].value == 40
    assert 0 < profile.fields["baselineCvr"].value <= 1
    assert profile.fields["baselineAur"].value > 0
    assert 0 < profile.fields["grossMargin"].value < 1

    # 40 stations x 30 days = 1200 station-days; a product-grain leak would
    # triple both the row count and the weekly traffic figure.
    traffic = profile.fields["weeklyStoreTraffic"]
    assert traffic.row_count == 1200
    assert traffic.value == pytest.approx(593.94 * 7, rel=0.01)


def test_unknown_channel_falls_back_to_digital():
    profile = get_baseline_profile("Walmart Banner Redesign", "carrier-pigeon")
    assert profile.channel == "digital"


def test_missing_dataset_returns_empty_profile(tmp_path):
    profile = profile_from_sample_data(tmp_path / "nope", "digital", "Anything")
    assert isinstance(profile, BaselineProfile)
    assert profile.fields == {}


def test_warehouse_probe_never_raises_on_a_bad_url():
    assert profile_from_warehouse("digital", "postgresql://nobody@127.0.0.1:1/none") is None
