from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd

from continum.ExpSuite.artifacts import MetricDelta, SliceFinding
from continum.ExpSuite.stats.statistics import proportion_test

logger = logging.getLogger("continum.analysis.segment")

STANDARD_DIMENSIONS = [
    "account_segment",
    "platform",
    "category",
    "country",
    "shipping_address_country",
]


def run_segment_analysis(
    df: pd.DataFrame,
    experiment_id: str,
    control_variant: str = "control",
    dimensions: Optional[List[str]] = None,
    alpha: float = 0.05,
    min_slice_n: int = 30,
) -> List[SliceFinding]:
    if df is None or len(df) == 0:
        return []

    if dimensions is None:
        dimensions = [c for c in STANDARD_DIMENSIONS if c in df.columns]

    variants = sorted(df["variant"].dropna().unique().tolist())
    treatments = [v for v in variants if v != control_variant]
    if not treatments:
        return []
    treatment = treatments[0]

    ctrl_df = df[df["variant"] == control_variant]
    treat_df = df[df["variant"] == treatment]

    # Overall effect
    overall_pr = proportion_test(
        len(ctrl_df),
        int(ctrl_df["converted_to_order"].fillna(0).sum()),
        len(treat_df),
        int(treat_df["converted_to_order"].fillna(0).sum()),
    )
    overall_delta = overall_pr["delta_pp"]

    slices: List[SliceFinding] = []
    for dim in dimensions:
        if dim not in df.columns:
            continue
        for level in df[dim].dropna().unique():
            c_sub = ctrl_df[ctrl_df[dim] == level]
            t_sub = treat_df[treat_df[dim] == level]
            if len(c_sub) < min_slice_n or len(t_sub) < min_slice_n:
                continue

            pr = proportion_test(
                len(c_sub),
                int(c_sub["converted_to_order"].fillna(0).sum()),
                len(t_sub),
                int(t_sub["converted_to_order"].fillna(0).sum()),
                alpha,
            )

            delta = MetricDelta(
                metric_name="inquiry_order_rate",
                metric_display_name=f"IOR — {dim}={level}",
                control_variant=control_variant,
                treatment_variant=treatment,
                n_control=len(c_sub),
                n_treatment=len(t_sub),
                rate_control=pr["rate_control"],
                rate_treatment=pr["rate_treatment"],
                delta_pp=pr["delta_pp"],
                delta_abs=pr["delta_abs"],
                delta_rel=pr["delta_rel"],
                ci_lo=pr["ci_lo"],
                ci_hi=pr["ci_hi"],
                p_value=pr["p_value"],
                effect_size=pr["effect_size_h"],
                is_significant=pr["is_significant"],
                direction=pr["direction"],
                alpha=alpha,
            )

            # Simpson's paradox: slice effect sign contradicts overall
            simpsons = pr["delta_pp"] * overall_delta < 0 and abs(pr["delta_pp"]) > 0.001

            slices.append(
                SliceFinding(
                    experiment_id=experiment_id,
                    metric_name="inquiry_order_rate",
                    dimension_name=dim,
                    dimension_value=str(level),
                    n_slice=len(c_sub) + len(t_sub),
                    delta=delta,
                    is_heterogeneous=pr["is_significant"],
                    simpsons_paradox_flag=simpsons,
                    interaction_p_value=pr["p_value"],
                )
            )

    if slices:
        logger.info(
            "Segment analysis: %d slices across %d dimensions for %s",
            len(slices),
            len(dimensions),
            experiment_id,
        )
    return slices


__all__ = ["run_segment_analysis"]
