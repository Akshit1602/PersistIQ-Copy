from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from continum.ExpSuite.artifacts import AnomalyReport, AnomalySeverity
from continum.ExpSuite.discovery.detectors import (
    WATCHTOWER_ALERT_Z,
    WATCHTOWER_BASELINE,
    cross_reference_experiments,
    detect_freshness,
    detect_null_spike,
    detect_schema_drift,
    detect_slice_anomaly,
    detect_volume_anomaly,
)

logger = logging.getLogger("continum.monitoring.monitors")
REQUIRED_SILVER_COLUMNS = [
    "created_at",
    "converted_to_order",
    "variant",
    "account_segment",
    "platform",
]
WATCHTOWER_DIMENSIONS = ["account_segment", "platform"]
WATCHTOWER_METRICS = [
    {"name": "IOR", "col": "converted_to_order", "agg": "mean"},
    {"name": "Volume", "col": "created_at", "agg": "count"},
]


def _make_report(
    anomaly_type, metric, dim, val, severity, z, baseline, observed, pct, action, xrefs=None
):
    return AnomalyReport(
        anomaly_type=anomaly_type,
        metric_affected=metric,
        dimension_name=dim,
        dimension_value=str(val),
        severity=AnomalySeverity(severity),
        detected_at=datetime.utcnow(),
        baseline_value=float(baseline or 0),
        observed_value=float(observed or 0),
        deviation_z_score=float(z or 0),
        pct_change=float(pct or 0),
        experiment_ids_concurrent=[x["experiment_name"] for x in (xrefs or [])[:2]],
        pipeline_hint="",
        recommended_action=str(action),
    )


class PipelineHealthMonitor:
    def __init__(self, db=None, sla_hours: float = 24.0):
        self.db = db
        self.sla_hours = sla_hours

    def run(self) -> List[AnomalyReport]:
        if self.db is None:
            return []
        try:
            df = self.db.execute("SELECT * FROM silver_inquiries LIMIT 100000").df()
        except Exception as e:
            logger.warning("PipelineHealthMonitor: %s", e)
            return []

        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

        reports: List[AnomalyReport] = []

        # 1. Volume drift
        try:
            if "created_at" in df.columns:
                daily = (
                    df.dropna(subset=["created_at"])
                    .groupby(df["created_at"].dt.normalize())
                    .size()
                    .sort_index()
                )
                if len(daily) > 3:
                    r = detect_volume_anomaly(daily)
                    if r["status"] == "analysed" and r["severity"] != "ok":
                        reports.append(
                            _make_report(
                                "volume_drift",
                                "inquiry_volume",
                                "overall",
                                "all",
                                r["severity"],
                                r["z_score"],
                                r["baseline_mean"],
                                r["today_value"],
                                r["pct_change"],
                                f"Volume: {r['today_value']:.0f} vs baseline {r['baseline_mean']:.0f} (z={r['z_score']:+.2f})",
                            )
                        )
        except Exception as e:
            logger.debug("Volume check: %s", e)

        # 2. Data freshness
        try:
            if "created_at" in df.columns:
                latest = df["created_at"].max()
                r = detect_freshness(latest, sla_hours=self.sla_hours)
                if r["severity"] != "ok":
                    _age = r.get("age_hours")
                    _age_msg = (
                        f"Data is {_age:.1f}h old (SLA={self.sla_hours}h). Check pipeline."
                        if _age is not None
                        else f"Data freshness unknown — no recent records (SLA={self.sla_hours}h). Check pipeline."
                    )
                    reports.append(
                        _make_report(
                            "freshness_sla",
                            "data_freshness",
                            "silver_inquiries",
                            "latest_record",
                            r["severity"],
                            None,
                            self.sla_hours,
                            _age,
                            None,
                            _age_msg,
                        )
                    )
        except Exception as e:
            logger.debug("Freshness check: %s", e)

        # 3. Null spike
        try:
            check_cols = [c for c in REQUIRED_SILVER_COLUMNS if c in df.columns]
            for spike in detect_null_spike(
                df, check_cols, {c: 0.0 for c in check_cols}, alert_pp=5.0
            ):
                reports.append(
                    _make_report(
                        "null_spike",
                        f"null_{spike['column']}",
                        "column",
                        spike["column"],
                        spike["severity"],
                        None,
                        spike["baseline_pct"],
                        spike["current_pct"],
                        spike["jump_pp"],
                        f"Null rate in '{spike['column']}' jumped +{spike['jump_pp']:.1f}pp. Inspect pipeline.",
                    )
                )
        except Exception as e:
            logger.debug("Null spike: %s", e)

        # 4. Schema drift
        try:
            r = detect_schema_drift(df.columns.tolist(), REQUIRED_SILVER_COLUMNS)
            if r["severity"] != "ok":
                reports.append(
                    _make_report(
                        "schema_drift",
                        "schema",
                        "silver_inquiries",
                        "schema",
                        r["severity"],
                        None,
                        None,
                        None,
                        None,
                        f"Schema changed. Missing: {r['missing_columns']}. New: {r['new_columns']}",
                    )
                )
        except Exception as e:
            logger.debug("Schema drift: %s", e)

        logger.info("PipelineHealthMonitor: %d report(s)", len(reports))
        return reports


class WatchtowerMonitor:
    def __init__(
        self,
        db=None,
        experiment_registry: Optional[List[Dict]] = None,
        baseline_days: int = WATCHTOWER_BASELINE,
        alert_z: float = WATCHTOWER_ALERT_Z,
    ):
        self.db = db
        self.experiment_registry = experiment_registry or []
        self.baseline_days = baseline_days
        self.alert_z = alert_z

    def run(self) -> List[AnomalyReport]:
        if self.db is None:
            return []
        try:
            df = self.db.execute(
                """
                SELECT created_at, converted_to_order, order_value, account_segment, platform
                FROM gold_experiment_analysis WHERE created_at IS NOT NULL LIMIT 200000
            """
            ).df()
        except Exception as e:
            logger.warning("WatchtowerMonitor: %s", e)
            return []

        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        df = df.dropna(subset=["created_at"])
        if df.empty:
            return []

        alerts: List[AnomalyReport] = []
        hist_end = df["created_at"].dt.normalize().max()

        for metric in WATCHTOWER_METRICS:
            for dim in WATCHTOWER_DIMENSIONS:
                if dim not in df.columns:
                    continue
                for level in df[dim].dropna().unique():
                    try:
                        sub = df[df[dim] == level]
                        col = metric["col"]
                        if col not in sub.columns:
                            continue
                        series = (
                            sub.dropna(subset=[col])
                            .groupby(sub["created_at"].dt.normalize())[col]
                            .mean()
                            if metric["agg"] == "mean"
                            else sub.groupby(sub["created_at"].dt.normalize())[col].count()
                        )
                        series = series.sort_index()
                        if len(series) < 5:
                            continue
                        r = detect_slice_anomaly(series, self.baseline_days, self.alert_z)
                        if r["status"] == "analysed" and r["severity"] in ("warning", "critical"):
                            xrefs = cross_reference_experiments(
                                dim, str(level), hist_end, self.experiment_registry
                            )
                            alerts.append(
                                _make_report(
                                    f"slice_{metric['name'].lower()}",
                                    metric["name"],
                                    dim,
                                    level,
                                    r["severity"],
                                    r["z_score"],
                                    r["baseline_mean"],
                                    r["today_value"],
                                    r["pct_change"],
                                    f"{metric['name']} anomaly: {dim}={level} z={r['z_score']:+.2f}",
                                    xrefs,
                                )
                            )
                    except Exception as e:
                        logger.debug("Watchtower slice %s=%s: %s", dim, level, e)

        alerts.sort(
            key=lambda a: (
                0 if a.severity == AnomalySeverity.CRITICAL else 1,
                -abs(a.deviation_z_score or 0),
            )
        )
        logger.info("WatchtowerMonitor: %d alert(s)", len(alerts))
        return alerts


class SequentialTester:
    def __init__(self, alpha: float = 0.05, planned_n: Optional[int] = None):
        from continum.ExpSuite.stats.sequential import SequentialTester as _ST

        self._tester = _ST(alpha=alpha, planned_n=planned_n)

    def update(self, *args, **kwargs):
        return self._tester.update(*args, **kwargs)

    def summary(self):
        return self._tester.summary()

    def run(self, db=None, **kwargs):
        return self._tester.run(db=db, **kwargs)
