from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from continum.runtime.config import RUNTIME_DATA_DIR, ensure_runtime_data_dir

logger = logging.getLogger("continum.runtime.memory")

ensure_runtime_data_dir()
MEMORY_DB_PATH = os.path.join(RUNTIME_DATA_DIR, "continum_memory.duckdb")


class CrossExperimentMemory:

    def __init__(self, db_path: str = MEMORY_DB_PATH, in_memory: bool = False):
        self.db_path   = db_path
        self._db       = None
        self._in_memory = in_memory
        self._conn     = None  # persistent connection for in-memory mode
        self._init_db()

    def _connect(self):
        import duckdb
        if self._in_memory:
            if self._conn is None:
                self._conn = duckdb.connect(":memory:")
            return self._conn
        return duckdb.connect(self.db_path)

    def _init_db(self) -> None:
        try:
            db = self._connect()
            db.execute("""
                CREATE TABLE IF NOT EXISTS experiment_memory (
                    experiment_id    VARCHAR,
                    experiment_name  VARCHAR,
                    recorded_at      VARCHAR,
                    phase            VARCHAR,
                    verdict          VARCHAR,
                    ship_recommendation VARCHAR,
                    primary_metric   VARCHAR,
                    delta_pp         DOUBLE,
                    p_value          DOUBLE,
                    is_significant   BOOLEAN,
                    n_total          INTEGER,
                    srm_detected     BOOLEAN,
                    tags             VARCHAR,
                    narrative        VARCHAR,
                    metadata         VARCHAR
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS anomaly_memory (
                    experiment_id    VARCHAR,
                    detected_at      VARCHAR,
                    anomaly_type     VARCHAR,
                    metric           VARCHAR,
                    severity         VARCHAR,
                    description      VARCHAR,
                    z_score          DOUBLE,
                    pct_change       DOUBLE,
                    resolved         BOOLEAN DEFAULT FALSE
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS metric_memory (
                    experiment_id    VARCHAR,
                    metric_name      VARCHAR,
                    baseline_value   DOUBLE,
                    observed_delta   DOUBLE,
                    is_significant   BOOLEAN,
                    recorded_at      VARCHAR
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS learning_memory (
                    experiment_id    VARCHAR,
                    recorded_at      VARCHAR,
                    category         VARCHAR,
                    learning         VARCHAR,
                    tags             VARCHAR
                )
            """)
            if not self._in_memory: db.close()
            if not self._in_memory:
                logger.info("CrossExperimentMemory initialised at %s", self.db_path)
        except Exception as e:
            logger.warning("Memory DB init failed (will use in-memory): %s", e)
            self._in_memory = True

    # ── Recording ──────────────────────────────────────────────────────────────

    def record_experiment(
        self,
        experiment_id: str,
        experiment_name: str,
        result: Any,
        narrative: str = "",
        tags: Optional[List[str]] = None,
        phase: str = "analysis",
    ) -> bool:
        try:
            db = self._connect()

            # Extract fields from result (pydantic or dict)
            def _get(obj, *keys, default=None):
                for k in keys:
                    try:
                        v = getattr(obj, k, None)
                        if v is not None:
                            return v
                    except Exception:
                        pass
                    try:
                        v = obj.get(k) if isinstance(obj, dict) else None
                        if v is not None:
                            return v
                    except Exception:
                        pass
                return default

            primary = _get(result, "primary_delta")
            delta_pp = float(_get(primary, "delta_pp", default=0.0) or 0.0)
            p_value  = float(_get(primary, "p_value", default=1.0) or 1.0)
            is_sig   = bool(_get(primary, "is_significant", default=False))
            n_total  = int(
                (_get(primary, "n_control", default=0) or 0) +
                (_get(primary, "n_treatment", default=0) or 0)
            )
            verdict  = str(_get(result, "verdict", default="") or "")
            ship_rec = str(_get(result, "ship_recommendation", default="") or "")
            metric   = str(_get(result, "primary_metric", default="") or "")
            srm      = bool(_get(result, "srm_detected", default=False))

            db.execute("""
                INSERT INTO experiment_memory VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [
                experiment_id,
                experiment_name,
                datetime.utcnow().isoformat(),
                phase,
                verdict,
                ship_rec,
                metric,
                delta_pp,
                p_value,
                is_sig,
                n_total,
                srm,
                json.dumps(tags or []),
                narrative[:2000],
                "{}",
            ])
            if not self._in_memory: db.close()
            logger.info("Experiment %s recorded to memory", experiment_id)
            return True
        except Exception as e:
            logger.warning("record_experiment failed: %s", e)
            return False

    def record_anomaly(
        self,
        experiment_id: str,
        anomaly_type: str,
        metric: str,
        severity: str,
        description: str,
        z_score: float = 0.0,
        pct_change: float = 0.0,
    ) -> None:
        try:
            db = self._connect()
            db.execute("""
                INSERT INTO anomaly_memory VALUES (?,?,?,?,?,?,?,?,?)
            """, [experiment_id, datetime.utcnow().isoformat(), anomaly_type,
                  metric, severity, description, z_score, pct_change, False])
            if not self._in_memory: db.close()
        except Exception as e:
            logger.debug("record_anomaly failed: %s", e)

    def record_metric(
        self,
        experiment_id: str,
        metric_name: str,
        baseline_value: float,
        observed_delta: float,
        is_significant: bool,
    ) -> None:
        try:
            db = self._connect()
            db.execute("""
                INSERT INTO metric_memory VALUES (?,?,?,?,?,?)
            """, [experiment_id, metric_name, baseline_value, observed_delta,
                  is_significant, datetime.utcnow().isoformat()])
            if not self._in_memory: db.close()
        except Exception as e:
            logger.debug("record_metric failed: %s", e)

    def record_learning(
        self,
        experiment_id: str,
        learning: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
    ) -> None:
        try:
            db = self._connect()
            db.execute("""
                INSERT INTO learning_memory VALUES (?,?,?,?,?)
            """, [experiment_id, datetime.utcnow().isoformat(), category,
                  learning[:2000], json.dumps(tags or [])])
            if not self._in_memory: db.close()
        except Exception as e:
            logger.debug("record_learning failed: %s", e)

    # ── Retrieval ──────────────────────────────────────────────────────────────

    def search_similar(self, topic: str, limit: int = 5) -> List[Dict]:
        try:
            db = self._connect()
            words = [w.lower() for w in topic.split() if len(w) > 2]
            if not words:
                return []
            conditions = " OR ".join([
                f"LOWER(experiment_name) LIKE '%{w}%' OR LOWER(narrative) LIKE '%{w}%'"
                for w in words[:5]
            ])
            rows = db.execute(f"""
                SELECT experiment_id, experiment_name, recorded_at, verdict,
                       ship_recommendation, primary_metric, delta_pp, p_value,
                       is_significant, narrative
                FROM experiment_memory
                WHERE {conditions}
                ORDER BY recorded_at DESC
                LIMIT {limit}
            """).fetchall()
            if not self._in_memory: db.close()
            cols = ["experiment_id", "experiment_name", "recorded_at", "verdict",
                    "ship_recommendation", "primary_metric", "delta_pp", "p_value",
                    "is_significant", "narrative"]
            return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            logger.debug("search_similar failed: %s", e)
            return []

    def get_learnings(self, metric: str = "", category: str = "", limit: int = 10) -> List[Dict]:
        try:
            db = self._connect()
            filters = []
            params  = []
            if metric:
                filters.append("LOWER(learning) LIKE ?")
                params.append(f"%{metric.lower()}%")
            if category:
                filters.append("LOWER(category) = ?")
                params.append(category.lower())
            where = f"WHERE {' AND '.join(filters)}" if filters else ""
            rows = db.execute(f"""
                SELECT experiment_id, recorded_at, category, learning, tags
                FROM learning_memory
                {where}
                ORDER BY recorded_at DESC
                LIMIT {limit}
            """, params).fetchall()
            if not self._in_memory: db.close()
            cols = ["experiment_id", "recorded_at", "category", "learning", "tags"]
            return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            logger.debug("get_learnings failed: %s", e)
            return []

    def get_successful_metrics(self, limit: int = 10) -> List[Dict]:
        try:
            db = self._connect()
            rows = db.execute(f"""
                SELECT metric_name,
                       COUNT(*) AS n_experiments,
                       AVG(observed_delta) AS avg_delta,
                       AVG(CASE WHEN is_significant THEN 1 ELSE 0 END) AS sig_rate
                FROM metric_memory
                WHERE is_significant = TRUE
                GROUP BY metric_name
                ORDER BY n_experiments DESC, sig_rate DESC
                LIMIT {limit}
            """).fetchall()
            if not self._in_memory: db.close()
            cols = ["metric_name", "n_experiments", "avg_delta", "sig_rate"]
            return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            logger.debug("get_successful_metrics failed: %s", e)
            return []

    def get_recent_anomalies(self, limit: int = 10, unresolved_only: bool = True) -> List[Dict]:
        try:
            db = self._connect()
            where = "WHERE resolved = FALSE" if unresolved_only else ""
            rows = db.execute(f"""
                SELECT experiment_id, detected_at, anomaly_type, metric, severity, description
                FROM anomaly_memory
                {where}
                ORDER BY detected_at DESC
                LIMIT {limit}
            """).fetchall()
            if not self._in_memory: db.close()
            cols = ["experiment_id", "detected_at", "anomaly_type", "metric", "severity", "description"]
            return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            logger.debug("get_recent_anomalies failed: %s", e)
            return []

    def experiment_count(self) -> int:
        try:
            db = self._connect()
            n = db.execute("SELECT COUNT(*) FROM experiment_memory").fetchone()[0]
            if not self._in_memory: db.close()
            return int(n)
        except Exception:
            return 0

    def render_summary(self) -> str:
        n = self.experiment_count()
        if n == 0:
            return "  📚 No experiments in memory yet."
        learnings = self.get_learnings(limit=1)
        anomalies = self.get_recent_anomalies(limit=1)
        lines = [f"  📚 {n} experiment(s) in memory"]
        if learnings:
            lines.append(f"  🧠 Latest learning: {learnings[0]['learning'][:60]}…")
        if anomalies:
            lines.append(f"  🔍 Recent anomaly: {anomalies[0]['description'][:60]}…")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

_MEMORY: Optional[CrossExperimentMemory] = None


def get_memory() -> CrossExperimentMemory:
    global _MEMORY
    if _MEMORY is None:
        _MEMORY = CrossExperimentMemory()
    return _MEMORY


__all__ = [
    "CrossExperimentMemory",
    "get_memory",
    "MEMORY_DB_PATH",
]
