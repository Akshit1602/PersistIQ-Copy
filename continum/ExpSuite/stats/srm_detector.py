from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.stats import chi2 as _chi2

logger = logging.getLogger("continum.experimentation.srm_detector")


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────


class SRMSeverity(str, Enum):
    NONE = "none"  # p > 0.05
    MILD = "mild"  # 0.01 < p ≤ 0.05
    MODERATE = "moderate"  # 0.001 < p ≤ 0.01
    SEVERE = "severe"  # p ≤ 0.001


@dataclass(frozen=True)
class SRMReport:
    srm_detected: bool
    severity: SRMSeverity
    chi2_stat: float
    g_stat: float
    p_value_chi2: float
    p_value_g: float
    p_value_combined: float  # Fisher's combined p
    observed_counts: Dict[str, int]
    expected_counts: Dict[str, float]
    observed_fractions: Dict[str, float]
    expected_fractions: Dict[str, float]
    relative_bias: Dict[str, float]  # (obs - exp) / exp per variant
    degrees_of_freedom: int
    n_total: int
    root_cause_hints: Tuple[str, ...]  # diagnostic messages
    dimensional_srm: Dict[str, "SRMReport"]  # SRM within each dimension


# ─────────────────────────────────────────────────────────────────────────────
# MAIN DETECTOR
# ─────────────────────────────────────────────────────────────────────────────


def detect_srm(
    variant_counts: Dict[str, int],
    expected_fractions: Optional[Dict[str, float]] = None,
    alpha: float = 0.01,  # stricter than standard 0.05
) -> SRMReport:
    variants = list(variant_counts.keys())
    observed = np.array([variant_counts[v] for v in variants], dtype=float)
    n_total = float(observed.sum())
    df = len(variants) - 1

    if n_total == 0:
        return _empty_report(variants)

    if expected_fractions is None:
        expected_fracs = {v: 1.0 / len(variants) for v in variants}
    else:
        s = sum(expected_fractions.values())
        expected_fracs = {v: expected_fractions.get(v, 1 / len(variants)) / s for v in variants}

    expected = np.array([expected_fracs[v] * n_total for v in variants])

    # ── Chi-square test ───────────────────────────────────────────────────────
    chi2_stat = float(np.sum((observed - expected) ** 2 / expected))
    p_chi2 = float(1 - _chi2.cdf(chi2_stat, df=df))

    # ── G-test (log-likelihood ratio) ────────────────────────────────────────
    # G = 2 * Σ O_i * ln(O_i / E_i)   — better calibrated for small counts
    with np.errstate(divide="ignore", invalid="ignore"):
        g_stat = float(
            2
            * np.sum(
                np.where(
                    observed > 0,
                    observed * np.log(observed / np.clip(expected, 1e-10, None)),
                    0.0,
                )
            )
        )
    p_g = float(1 - _chi2.cdf(g_stat, df=df))

    # ── Fisher's combined p (meta-analysis of two test statistics) ───────────
    # -2 * (log(p1) + log(p2)) ~ chi2(4)
    p_combined = _fisher_combined_p([p_chi2, p_g], df=2)

    srm_detected = bool(p_combined < alpha)
    severity = _classify_severity(p_combined)

    # ── Relative bias per variant ─────────────────────────────────────────────
    rel_bias = {
        v: round(
            (variant_counts[v] - float(expected_fracs[v] * n_total))
            / max(float(expected_fracs[v] * n_total), 1),
            4,
        )
        for v in variants
    }

    # ── Root cause hints ──────────────────────────────────────────────────────
    hints = _root_cause_hints(variants, observed, expected, rel_bias)

    logger.info(
        "SRM[%s]: χ²=%.3f G=%.3f p_combined=%.4f severity=%s",
        "/".join(variants),
        chi2_stat,
        g_stat,
        p_combined,
        severity.value,
    )

    return SRMReport(
        srm_detected=srm_detected,
        severity=severity,
        chi2_stat=round(chi2_stat, 4),
        g_stat=round(g_stat, 4),
        p_value_chi2=round(p_chi2, 6),
        p_value_g=round(p_g, 6),
        p_value_combined=round(p_combined, 6),
        observed_counts={v: int(variant_counts[v]) for v in variants},
        expected_counts={v: round(float(e), 1) for v, e in zip(variants, expected)},
        observed_fractions={v: round(float(variant_counts[v]) / n_total, 4) for v in variants},
        expected_fractions={v: round(float(expected_fracs[v]), 4) for v in variants},
        relative_bias=rel_bias,
        degrees_of_freedom=df,
        n_total=int(n_total),
        root_cause_hints=tuple(hints),
        dimensional_srm={},
    )


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSIONAL SRM (per segment / platform)
# ─────────────────────────────────────────────────────────────────────────────


def detect_dimensional_srm(
    df,  # pandas DataFrame
    variant_col: str = "variant",
    dimensions: Optional[List[str]] = None,
    alpha: float = 0.01,
) -> Dict[str, SRMReport]:
    results = {}
    if dimensions is None:
        dimensions = [c for c in ["account_segment", "platform", "country"] if c in df.columns]

    overall_counts = dict(df[variant_col].value_counts())
    n_variants = len(overall_counts)
    expected_fracs = {v: 1.0 / n_variants for v in overall_counts}

    for dim in dimensions:
        if dim not in df.columns:
            continue
        for level in df[dim].dropna().unique():
            sub = df[df[dim] == level]
            counts = dict(sub[variant_col].value_counts())
            if sum(counts.values()) < 20:
                continue
            # Expected fraction: same as overall split
            report = detect_srm(counts, expected_fracs, alpha)
            if report.srm_detected:
                results[f"{dim}={level}"] = report

    return results


# ─────────────────────────────────────────────────────────────────────────────
# TIME-SERIES SRM (assignment rate over time)
# ─────────────────────────────────────────────────────────────────────────────


def detect_temporal_srm(
    assignment_timestamps: Dict[str, Sequence],  # {"variant": [t1, t2, ...]}
    alpha: float = 0.05,
    n_windows: int = 7,
) -> Dict:
    import pandas as pd

    variants = list(assignment_timestamps.keys())
    if not variants:
        return {"error": "no data"}

    # Build daily counts
    min_t = min(min(ts) for ts in assignment_timestamps.values() if len(ts) > 0)
    max_t = max(max(ts) for ts in assignment_timestamps.values() if len(ts) > 0)

    try:
        dates = pd.date_range(pd.Timestamp(min_t), pd.Timestamp(max_t), periods=n_windows + 1)
    except Exception:
        return {"error": "could not parse timestamps"}

    window_reports = []
    any_srm = False
    for i in range(len(dates) - 1):
        lo, hi = dates[i], dates[i + 1]
        window_counts = {}
        for v in variants:
            ts = pd.to_datetime(assignment_timestamps[v])
            window_counts[v] = int(((ts >= lo) & (ts < hi)).sum())
        report = detect_srm(window_counts, alpha=alpha)
        window_reports.append(
            {
                "window": f"{lo.date()} – {hi.date()}",
                "counts": window_counts,
                "srm": report.srm_detected,
                "p_combined": report.p_value_combined,
            }
        )
        if report.srm_detected:
            any_srm = True

    return {
        "temporal_srm_detected": any_srm,
        "n_windows_with_srm": sum(1 for w in window_reports if w["srm"]),
        "window_reports": window_reports,
    }


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _classify_severity(p: float) -> SRMSeverity:
    if p > 0.05:
        return SRMSeverity.NONE
    if p > 0.01:
        return SRMSeverity.MILD
    if p > 0.001:
        return SRMSeverity.MODERATE
    return SRMSeverity.SEVERE


def _fisher_combined_p(p_values: List[float], df: int = 2) -> float:
    pvals = [max(p, 1e-300) for p in p_values]
    chi2_combined = -2 * sum(np.log(p) for p in pvals)
    return float(1 - _chi2.cdf(chi2_combined, df=2 * len(pvals)))


def _root_cause_hints(
    variants: List[str],
    observed: np.ndarray,
    expected: np.ndarray,
    rel_bias: Dict[str, float],
) -> List[str]:
    hints = []

    # Which variants are over/under-represented?
    over = [v for v in variants if rel_bias.get(v, 0) > 0.05]
    under = [v for v in variants if rel_bias.get(v, 0) < -0.05]

    if over:
        hints.append(
            f"Over-represented: {over}. "
            "Check: bot traffic hitting treatment more, bucketing collisions."
        )
    if under:
        hints.append(
            f"Under-represented: {under}. "
            "Check: user-level vs session-level assignment mismatch, "
            "cookie deletion disproportionately affecting this arm."
        )

    max_bias = max(abs(b) for b in rel_bias.values()) if rel_bias else 0
    if max_bias > 0.20:
        hints.append(
            f"Large relative bias ({max_bias:.0%}): likely a code bug, "
            "sticky bucketing issue, or traffic filter applied post-assignment."
        )
    elif max_bias > 0.05:
        hints.append(
            f"Moderate relative bias ({max_bias:.0%}): consider checking "
            "Statsig/LaunchDarkly assignment logs for the affected window."
        )

    if len(variants) == 2:
        # Two-arm SRM often caused by triggering condition differences
        hints.append(
            "Two-arm SRM: common causes include (1) early-stopping/hold-back "
            "rules that apply to only one arm, (2) redirect-based assignment "
            "where one arm sees fewer page loads due to caching."
        )

    return hints


def _empty_report(variants: List[str]) -> SRMReport:
    return SRMReport(
        srm_detected=False,
        severity=SRMSeverity.NONE,
        chi2_stat=0.0,
        g_stat=0.0,
        p_value_chi2=1.0,
        p_value_g=1.0,
        p_value_combined=1.0,
        observed_counts={v: 0 for v in variants},
        expected_counts={v: 0.0 for v in variants},
        observed_fractions={v: 0.0 for v in variants},
        expected_fractions={v: 1 / len(variants) for v in variants},
        relative_bias={v: 0.0 for v in variants},
        degrees_of_freedom=max(len(variants) - 1, 1),
        n_total=0,
        root_cause_hints=("No data",),
        dimensional_srm={},
    )


__all__ = [
    "SRMSeverity",
    "SRMReport",
    "detect_srm",
    "detect_dimensional_srm",
    "detect_temporal_srm",
]
