import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# RAW OBSERVATION ARRAYS
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def rng():
    return np.random.default_rng(42)


@pytest.fixture(scope="session")
def null_experiment(rng):
    n = 2000
    ctrl = rng.binomial(1, 0.18, n)
    treat = rng.binomial(1, 0.18, n)
    return {"ctrl": ctrl, "treat": treat, "n": n, "true_rate_ctrl": 0.18, "true_rate_treat": 0.18}


@pytest.fixture(scope="session")
def positive_experiment(rng):
    n = 5000
    ctrl = rng.binomial(1, 0.18, n)
    treat = rng.binomial(1, 0.20, n)
    return {
        "ctrl": ctrl,
        "treat": treat,
        "n": n,
        "true_rate_ctrl": 0.18,
        "true_rate_treat": 0.20,
        "true_delta_pp": 2.0,
    }


@pytest.fixture(scope="session")
def negative_experiment(rng):
    n = 5000
    ctrl = rng.binomial(1, 0.20, n)
    treat = rng.binomial(1, 0.17, n)
    return {"ctrl": ctrl, "treat": treat, "n": n, "true_rate_ctrl": 0.20, "true_rate_treat": 0.17}


@pytest.fixture(scope="session")
def revenue_arrays(rng):
    n = 2000
    ctrl = rng.exponential(4000, n)
    treat = rng.exponential(4200, n)
    return {"ctrl": ctrl, "treat": treat, "true_mean_ctrl": 4000.0, "true_mean_treat": 4200.0}


@pytest.fixture(scope="session")
def cuped_arrays(rng):
    n = 2000
    pre_ctrl = rng.normal(0.18, 0.05, n)
    pre_treat = rng.normal(0.18, 0.05, n)
    # Post = noise + signal from pre + treatment effect
    noise_c = rng.normal(0, 0.03, n)
    noise_t = rng.normal(0, 0.03, n)
    post_ctrl = np.clip(0.4 * pre_ctrl + 0.6 * 0.18 + noise_c, 0, 1)
    post_treat = np.clip(0.4 * pre_treat + 0.6 * 0.18 + noise_t + 0.02, 0, 1)
    return {
        "post_ctrl": post_ctrl,
        "post_treat": post_treat,
        "pre_ctrl": pre_ctrl,
        "pre_treat": pre_treat,
        "true_delta": 0.02,
    }


@pytest.fixture(scope="session")
def experiment_df(rng):
    n = 1200
    variant = rng.choice(["control", "treatment"], size=n)
    converted = np.where(
        variant == "treatment",
        rng.binomial(1, 0.20, n),
        rng.binomial(1, 0.18, n),
    )
    return pd.DataFrame(
        {
            "experiment_name": "test_exp_v1",
            "variant": variant,
            "converted_to_order": converted,
            "order_value": np.where(converted == 1, rng.exponential(4000, n), 0.0),
            "created_at": pd.date_range("2025-01-01", periods=n, freq="h"),
            "account_segment": rng.choice(["Core", "Growth", "Enterprise", "Individuals"], n),
            "platform": rng.choice(["web", "mobile"], n),
        }
    )


@pytest.fixture(scope="session")
def balanced_srm_counts():
    return {"control": 5000, "treatment": 5000}


@pytest.fixture(scope="session")
def imbalanced_srm_counts():
    return {"control": 5000, "treatment": 3500}
