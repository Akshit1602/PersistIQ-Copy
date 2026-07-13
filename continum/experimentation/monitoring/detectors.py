from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import chisquare as _chisquare

logger = logging.getLogger("continum.monitoring.detectors")

WATCHTOWER_BASELINE = 28  # days of history for DOW-adjusted baseline
WATCHTOWER_ALERT_Z = 3.0  # |z| threshold for anomaly
SLA_HOURS_DEFAULT = 24  # max acceptable data age
NULL_ALERT_PP = 10.0  # pp jump in null rate triggers alert


# ─────────────────────────────────────────────────────────────────────────────
# 1. VOLUME ANOMALY
# ─────────────────────────────────────────────────────────────────────────────


def detect_volume_anomaly(
    daily_series: "pd.Series",  # DatetimeIndex → count
    baseline_days: int = WATCHTOWER_BASELINE,
    alert_z: float = WATCHTOWER_ALERT_Z,
) -> Dict:
    if len(daily_series) < 3:
        return {"status": "insufficient_data", "severity": "info"}

    today_val = float(daily_series.iloc[-1])
    if pd.isna(today_val):
        return {"status": "no_data", "severity": "warning"}

    history = daily_series.iloc[-(baseline_days + 1) : -1]
    if len(history) == 0:
        return {"status": "insufficient_data", "severity": "info"}

    today_dow = daily_series.index[-1].dayofweek
    same_dow = history[history.index.dayofweek == today_dow]
    if len(same_dow) >= 3:
        baseline_mean = float(same_dow.mean())
        baseline_std = float(same_dow.std(ddof=1)) or 1.0
    else:
        baseline_mean = float(history.mean())
        baseline_std = float(history.std(ddof=1)) or 1.0

    z = (today_val - baseline_mean) / baseline_std
    pct_change = (today_val - baseline_mean) / baseline_mean * 100 if baseline_mean else 0.0
    severity = "critical" if abs(z) > alert_z else "warning" if abs(z) > 1.5 else "ok"

    return {
        "status": "analysed",
        "today_value": round(today_val, 2),
        "baseline_mean": round(baseline_mean, 2),
        "baseline_std": round(baseline_std, 2),
        "z_score": round(z, 3),
        "pct_change": round(pct_change, 2),
        "severity": severity,
        "baseline_days": baseline_days,
        "n_same_dow": len(same_dow),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. DISTRIBUTION SHIFT
# ─────────────────────────────────────────────────────────────────────────────


def detect_distribution_shift(
    today_counts: "pd.Series",  # category → count for the recent period
    baseline_counts: "pd.Series",  # category → count for the baseline period
    alert_p: float = 0.001,
) -> Dict:
    today = today_counts.reindex(baseline_counts.index, fill_value=0).astype(float)
    if today.sum() == 0 or baseline_counts.sum() == 0:
        return {"status": "insufficient_data", "severity": "info"}

    expected = baseline_counts / baseline_counts.sum() * today.sum()
    expected = expected.replace(0, 1e-6)

    chi2, p = _chisquare(today.values, f_exp=expected.values)
    severity = "critical" if p < alert_p else "warning" if p < 0.01 else "ok"

    # Which categories shifted most?
    abs_shifts = {
        k: round(
            float(
                today.get(k, 0) / today.sum() - baseline_counts.get(k, 0) / baseline_counts.sum()
            ),
            4,
        )
        for k in baseline_counts.index
    }
    biggest_shift = max(abs_shifts, key=lambda k: abs(abs_shifts[k]), default=None)

    return {
        "status": "analysed",
        "chi2": round(float(chi2), 3),
        "p_value": round(float(p), 6),
        "severity": severity,
        "biggest_shift": biggest_shift,
        "category_shifts": abs_shifts,
        "today_split": {k: int(v) for k, v in today.items()},
        "baseline_split": {k: int(v) for k, v in baseline_counts.items()},
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. DATA FRESHNESS
# ─────────────────────────────────────────────────────────────────────────────


def detect_freshness(
    latest_ts,
    sla_hours: float = SLA_HOURS_DEFAULT,
) -> Dict:
    if latest_ts is None or pd.isna(latest_ts):
        return {
            "status": "no_data",
            "latest": "n/a",
            "age_hours": None,
            "sla_hours": sla_hours,
            "severity": "critical",
        }
    try:
        age_hours = (pd.Timestamp.now() - pd.Timestamp(latest_ts)).total_seconds() / 3600
    except Exception:
        return {"status": "parse_error", "severity": "warning", "sla_hours": sla_hours}

    severity = (
        "critical" if age_hours > sla_hours * 2 else "warning" if age_hours > sla_hours else "ok"
    )
    return {
        "status": "analysed",
        "latest": str(latest_ts),
        "age_hours": round(age_hours, 2),
        "sla_hours": sla_hours,
        "severity": severity,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. NULL SPIKE
# ─────────────────────────────────────────────────────────────────────────────


def detect_null_spike(
    df: "pd.DataFrame",
    columns: List[str],
    baseline_null_rates: Dict[str, float],  # col → baseline null % (0-100)
    alert_pp: float = NULL_ALERT_PP,
) -> List[Dict]:
    findings = []
    for col in columns:
        if col not in df.columns:
            continue
        current = df[col].isna().mean() * 100
        baseline = baseline_null_rates.get(col, 0.0)
        jump = current - baseline
        if jump > alert_pp:
            findings.append(
                {
                    "column": col,
                    "baseline_pct": round(baseline, 2),
                    "current_pct": round(current, 2),
                    "jump_pp": round(jump, 2),
                    "severity": "critical" if jump > alert_pp * 2 else "warning",
                }
            )
    return findings


# ─────────────────────────────────────────────────────────────────────────────
# 5. SCHEMA DRIFT
# ─────────────────────────────────────────────────────────────────────────────


def detect_schema_drift(
    current_columns: List[str],
    expected_columns: List[str],
) -> Dict:
    current_set = set(c.lower() for c in current_columns)
    expected_set = set(c.lower() for c in expected_columns)
    new_cols = sorted(current_set - expected_set)
    missing_cols = sorted(expected_set - current_set)
    severity = "critical" if missing_cols else "warning" if new_cols else "ok"
    return {
        "new_columns": new_cols,
        "missing_columns": missing_cols,
        "n_new": len(new_cols),
        "n_missing": len(missing_cols),
        "severity": severity,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. SLICE ANOMALY (Watchtower per-slice)
# ─────────────────────────────────────────────────────────────────────────────


def detect_slice_anomaly(
    series: "pd.Series",  # DatetimeIndex → metric value (daily)
    baseline_days: int = WATCHTOWER_BASELINE,
    alert_z: float = WATCHTOWER_ALERT_Z,
) -> Dict:
    if len(series) < baseline_days + 1:
        return {"status": "insufficient_data", "severity": "info"}

    history = series.iloc[-(baseline_days + 1) : -1]
    today_val = float(series.iloc[-1])
    if pd.isna(today_val):
        return {"status": "no_data", "severity": "warning"}

    today_dow = series.index[-1].dayofweek
    same_dow = history[history.index.dayofweek == today_dow]
    if len(same_dow) >= 3:
        baseline_mean = float(same_dow.mean())
        baseline_std = float(same_dow.std(ddof=1)) or 1.0
    else:
        baseline_mean = float(history.mean())
        baseline_std = float(history.std(ddof=1)) or 1.0

    z = (today_val - baseline_mean) / baseline_std
    pct_change = (today_val - baseline_mean) / baseline_mean * 100 if baseline_mean else 0.0
    severity = "critical" if abs(z) > alert_z else "warning" if abs(z) > 1.5 else "ok"
    return {
        "status": "analysed",
        "today_value": round(today_val, 6),
        "baseline_mean": round(baseline_mean, 6),
        "z_score": round(z, 3),
        "pct_change": round(pct_change, 2),
        "severity": severity,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. CROSS-REFERENCE
# ─────────────────────────────────────────────────────────────────────────────


def cross_reference_experiments(
    anomaly_dim: str,
    anomaly_level: str,
    anomaly_date: "pd.Timestamp",
    experiment_registry: List[Dict],
) -> List[Dict]:
    matches = []
    for exp in experiment_registry:
        if exp.get("status") not in ("running", "concluded"):
            continue
        try:
            start = pd.Timestamp(exp["start_date"])
            end = pd.Timestamp(exp["end_date"]) if exp.get("end_date") else pd.Timestamp.now()
        except Exception:
            continue
        if start <= anomaly_date <= end:
            matches.append(
                {
                    "experiment_name": exp["experiment_name"],
                    "status": exp["status"],
                    "start": str(exp["start_date"]),
                    "end": str(exp.get("end_date", "ongoing")),
                }
            )
    return matches


def cross_reference_pipeline_baseline(
    metric_name: str,
    pipeline_baseline: Optional[Dict],
) -> str:
    if not pipeline_baseline:
        return ""
    overall = str(pipeline_baseline.get("overall", ""))
    if metric_name.lower() == "volume":
        if "critical" in overall.lower():
            return "⚠️  Pipeline baseline was CRITICAL — this may be a data issue, not a business signal"
        if "warning" in overall.lower():
            return "⚠️  Pipeline baseline was WARNING — check data pipeline before acting"
    return ""


def profile_dataframe(
    df: "pd.DataFrame",
    table_name: str = "table",
    sample_size: int = 2000,
) -> Dict:
    df_sample = (
        df.sample(min(sample_size, len(df)), random_state=42) if len(df) > sample_size else df
    )
    n = len(df_sample)
    cols = {}
    for col in df_sample.columns:
        s = df_sample[col]
        null_rate = float(s.isna().mean())
        n_unique = int(s.nunique())
        dtype_str = str(s.dtype)
        try:
            is_numeric = np.issubdtype(s.dtype, np.number)
        except TypeError:
            is_numeric = False
        entry: Dict[str, Any] = {
            "dtype": dtype_str,
            "null_rate": round(null_rate, 4),
            "null_pct": round(null_rate * 100, 2),
            "n_unique": n_unique,
            "n_sampled": n,
            "is_likely_pk": n_unique / max(n, 1) > 0.95 and null_rate < 0.01,
            "is_likely_cat": n_unique < 30 and null_rate < 0.5 and not is_numeric,
        }
        if is_numeric:
            clean = s.dropna().astype(float)
            if len(clean) > 0:
                entry.update(
                    {
                        "mean": round(float(clean.mean()), 4),
                        "median": round(float(clean.median()), 4),
                        "std": round(float(clean.std()), 4),
                        "min": round(float(clean.min()), 4),
                        "max": round(float(clean.max()), 4),
                        "p25": round(float(np.percentile(clean, 25)), 4),
                        "p75": round(float(np.percentile(clean, 75)), 4),
                        "p99": round(float(np.percentile(clean, 99)), 4),
                        "n_zero": int((clean == 0).sum()),
                        "n_neg": int((clean < 0).sum()),
                    }
                )
        else:
            top_vals = s.dropna().value_counts().head(5).to_dict()
            entry["top_values"] = {str(k): int(v) for k, v in top_vals.items()}
        try:
            entry["sample"] = s.dropna().head(3).tolist()
        except Exception:
            entry["sample"] = []
        cols[col] = entry

    # Detect likely date columns
    date_cols = [
        c
        for c in df_sample.columns
        if any(k in c.lower() for k in ("date", "time", "at", "created", "updated", "ts"))
    ]

    return {
        "table_name": table_name,
        "n_rows_total": len(df),
        "n_rows_sampled": n,
        "n_cols": len(cols),
        "columns": cols,
        "likely_date_cols": date_cols,
        "n_null_heavy": sum(1 for c in cols.values() if c["null_rate"] > 0.20),
        "n_likely_pk": sum(1 for c in cols.values() if c.get("is_likely_pk")),
        "n_likely_cat": sum(1 for c in cols.values() if c.get("is_likely_cat")),
    }


__all__ = [
    "detect_volume_anomaly",
    "detect_distribution_shift",
    "detect_freshness",
    "detect_null_spike",
    "detect_schema_drift",
    "detect_slice_anomaly",
    "cross_reference_experiments",
    "cross_reference_pipeline_baseline",
    "profile_dataframe",
]
