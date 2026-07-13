from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import stats

logger = logging.getLogger("continum.experimentation.sequential")

# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SequentialState:
    n_ctrl: int
    n_treat: int
    conv_ctrl: int
    conv_treat: int
    e_value: float  # mSPRT e-value
    p_value_valid: float  # always-valid p-value (1/e)
    rate_ctrl: float
    rate_treat: float
    delta_pp: float
    cs_lo: float  # confidence sequence lower bound
    cs_hi: float  # confidence sequence upper bound
    boundary_crossed: bool
    alpha: float
    n_looks: int  # how many times we've checked
    spent_alpha: float  # alpha spent so far (O'Brien-Fleming)


# ─────────────────────────────────────────────────────────────────────────────
# mSPRT E-VALUE
# ─────────────────────────────────────────────────────────────────────────────


def compute_e_value(
    n_ctrl: int,
    conv_ctrl: int,
    n_treat: int,
    conv_treat: int,
    null_delta: float = 0.0,
    mixing_var: float = 0.25,  # variance of the Gaussian mixing distribution
) -> float:
    if n_ctrl <= 0 or n_treat <= 0:
        return 1.0

    p_c = conv_ctrl / n_ctrl
    p_t = conv_treat / n_treat
    obs_delta = p_t - p_c - null_delta

    # Pooled SE under null
    p_pool = (conv_ctrl + conv_treat) / (n_ctrl + n_treat)
    var_pool = p_pool * (1 - p_pool) * (1 / n_ctrl + 1 / n_treat)
    if var_pool <= 0:
        return 1.0

    # Gaussian e-value (mSPRT with Gaussian mixing)
    # E_t = (1 + t/v)^{-1/2} * exp( (t * delta_t)^2 / (2 * v_t * (1 + t/v)) )
    # where t = 1/var_pool, v = 1/mixing_var
    t = 1.0 / var_pool
    v = 1.0 / mixing_var
    e_val = float(np.sqrt(v / (v + t)) * np.exp(0.5 * t**2 * obs_delta**2 / (v + t)))
    return float(max(e_val, 0.0))


def e_value_to_p(e_value: float) -> float:
    return float(min(1.0, 1.0 / max(e_value, 1e-10)))


# ─────────────────────────────────────────────────────────────────────────────
# ALWAYS-VALID CONFIDENCE SEQUENCE (Howard et al. 2021, time-uniform CLT)
# ─────────────────────────────────────────────────────────────────────────────


def confidence_sequence(
    n_ctrl: int,
    conv_ctrl: int,
    n_treat: int,
    conv_treat: int,
    alpha: float = 0.05,
    t_opt: Optional[int] = None,  # planned sample size (sets prior width)
) -> Tuple[float, float]:
    p_c = conv_ctrl / n_ctrl if n_ctrl > 0 else 0.5
    p_t = conv_treat / n_treat if n_treat > 0 else 0.5
    delta = p_t - p_c

    n = n_ctrl + n_treat
    if n == 0:
        return (-1.0, 1.0)

    # Pooled SE
    p_pool = (conv_ctrl + conv_treat) / (n_ctrl + n_treat)
    se = float(np.sqrt(p_pool * (1 - p_pool) * (1 / max(n_ctrl, 1) + 1 / max(n_treat, 1))))

    if t_opt is None:
        t_opt = max(n * 4, 1000)  # default: assume we're ~25% through

    # Time-uniform bound (simplified Howard et al.)
    rho = float(np.sqrt(alpha * np.e / t_opt))
    rho = float(np.clip(rho, 1e-6, 0.5))
    log_term = float(np.log(1 / rho**2))
    inner = max(log_term + np.log(max(log_term, 1e-10)) + 2, 0.1)
    width = float(np.sqrt(rho**2 / max(n, 1) * inner))
    # Scale by SE
    half_width = max(se * width * float(np.sqrt(n)), se * float(np.sqrt(2 * np.log(2 / alpha))))

    return (
        round(float(delta - half_width), 6),
        round(float(delta + half_width), 6),
    )


# ─────────────────────────────────────────────────────────────────────────────
# OBRIEN-FLEMING ALPHA SPENDING
# ─────────────────────────────────────────────────────────────────────────────


def obrien_fleming_boundary(
    n_looks: int,
    look_times: Sequence[float],  # information fractions at each look [0,1]
    alpha: float = 0.05,
) -> List[Dict]:
    z_final = float(stats.norm.ppf(1 - alpha / 2))
    boundaries = []
    alpha_spent_total = 0.0
    for i, t in enumerate(look_times):
        if t <= 0:
            continue
        z_boundary = z_final / float(np.sqrt(t))
        alpha_at_look = float(2 * stats.norm.sf(z_boundary))
        alpha_incremental = max(0.0, alpha_at_look - alpha_spent_total)
        alpha_spent_total = alpha_at_look
        boundaries.append(
            {
                "look": i + 1,
                "information_frac": round(t, 4),
                "z_boundary": round(z_boundary, 4),
                "alpha_spent_total": round(alpha_at_look, 6),
                "alpha_incremental": round(alpha_incremental, 6),
                "p_threshold": round(alpha_at_look, 6),
            }
        )
    return boundaries


# ─────────────────────────────────────────────────────────────────────────────
# SEQUENTIAL TEST RUNNER (stateful)
# ─────────────────────────────────────────────────────────────────────────────


class SequentialTester:

    def __init__(
        self,
        alpha: float = 0.05,
        planned_n: Optional[int] = None,
        mixing_var: float = 0.25,
    ):
        self.alpha = alpha
        self.planned_n = planned_n
        self.mixing_var = mixing_var
        self.threshold = 1.0 / alpha
        self._e_history: List[float] = []
        self._n_history: List[int] = []
        self._delta_history: List[float] = []
        self._n_looks: int = 0

    def update(
        self,
        n_ctrl: int,
        conv_ctrl: int,
        n_treat: int,
        conv_treat: int,
    ) -> SequentialState:
        self._n_looks += 1
        n_total = n_ctrl + n_treat

        e_val = compute_e_value(
            n_ctrl,
            conv_ctrl,
            n_treat,
            conv_treat,
            mixing_var=self.mixing_var,
        )
        self._e_history.append(e_val)
        self._n_history.append(n_total)

        p_c = conv_ctrl / n_ctrl if n_ctrl > 0 else 0.0
        p_t = conv_treat / n_treat if n_treat > 0 else 0.0
        delta = (p_t - p_c) * 100
        self._delta_history.append(delta)

        cs_lo, cs_hi = confidence_sequence(
            n_ctrl,
            conv_ctrl,
            n_treat,
            conv_treat,
            alpha=self.alpha,
            t_opt=self.planned_n,
        )
        p_valid = e_value_to_p(e_val)
        spent = float(
            2
            * stats.norm.sf(
                stats.norm.ppf(1 - self.alpha / 2) / float(np.sqrt(max(self._n_looks, 1)))
            )
        )

        return SequentialState(
            n_ctrl=n_ctrl,
            n_treat=n_treat,
            conv_ctrl=conv_ctrl,
            conv_treat=conv_treat,
            e_value=round(e_val, 4),
            p_value_valid=round(p_valid, 6),
            rate_ctrl=round(p_c, 6),
            rate_treat=round(p_t, 6),
            delta_pp=round(delta, 4),
            cs_lo=cs_lo,
            cs_hi=cs_hi,
            boundary_crossed=bool(e_val >= self.threshold),
            alpha=self.alpha,
            n_looks=self._n_looks,
            spent_alpha=round(spent, 6),
        )

    @property
    def e_history(self) -> List[float]:
        return list(self._e_history)

    @property
    def n_history(self) -> List[int]:
        return list(self._n_history)

    def summary(self) -> Dict:
        if not self._e_history:
            return {"error": "no data — call update() first"}
        latest = self._e_history[-1]
        return {
            "n_looks": self._n_looks,
            "current_e_value": round(latest, 4),
            "current_p_valid": round(e_value_to_p(latest), 6),
            "threshold": round(self.threshold, 2),
            "boundary_crossed": bool(latest >= self.threshold),
            "max_e_value": round(max(self._e_history), 4),
            "alpha": self.alpha,
        }

    def run(self, db=None, experiment_name: str = "", **kwargs) -> Dict:
        if db is None:
            return {"error": "No database connection"}
        try:
            df = db.execute(f"""
                SELECT variant,
                       COUNT(*)                               AS n_obs,
                       SUM(CAST(converted_to_order AS INT))  AS n_conv
                FROM gold_experiment_analysis
                WHERE experiment_name = '{experiment_name}'
                  AND variant IS NOT NULL
                GROUP BY variant
            """).df()
        except Exception as e:
            return {"error": str(e)}

        if df.empty:
            return {"error": f"No data for experiment {experiment_name!r}"}

        variants = df["variant"].tolist()
        control = next((v for v in variants if "control" in v.lower()), variants[0])
        results = {}
        for _, row in df.iterrows():
            if row["variant"] == control:
                continue
            ctrl_row = df[df["variant"] == control].iloc[0]
            state = self.update(
                int(ctrl_row["n_obs"]),
                int(ctrl_row["n_conv"]),
                int(row["n_obs"]),
                int(row["n_conv"]),
            )
            results[row["variant"]] = {
                "e_value": state.e_value,
                "p_value_valid": state.p_value_valid,
                "delta_pp": state.delta_pp,
                "cs_lo_pp": round(state.cs_lo * 100, 4),
                "cs_hi_pp": round(state.cs_hi * 100, 4),
                "boundary_crossed": state.boundary_crossed,
            }
        return {
            "experiment": experiment_name,
            "alpha": self.alpha,
            "threshold": self.threshold,
            "results": results,
        }


__all__ = [
    "SequentialState",
    "SequentialTester",
    "compute_e_value",
    "e_value_to_p",
    "confidence_sequence",
    "obrien_fleming_boundary",
]
