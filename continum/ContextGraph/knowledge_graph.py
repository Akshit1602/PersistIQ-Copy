from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("continum.knowledge_graph")


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

NODE_TYPES = {
    "Experiment": ["id", "name", "status", "owner", "team", "feature_area", "primary_metric"],
    "Hypothesis": ["id", "statement", "domain", "confidence", "owner"],
    "Metric": ["name", "direction", "metric_type", "owner"],
    "Segment": ["name", "entity_type", "estimated_size", "owner"],
    "Learning": ["id", "statement", "domain", "confidence", "evidence_type"],
    "Anomaly": ["id", "anomaly_type", "metric", "severity", "detected_at", "resolved"],
    "CausalOutput": ["id", "method", "estimand", "estimate", "ci_lo", "ci_hi", "p_value"],
    "Owner": ["name", "team"],
    "Document": ["id", "type", "title", "created_at"],
}

EDGE_TYPES = {
    "TESTS": ("Experiment", "Hypothesis"),
    "MEASURES": ("Experiment", "Metric"),
    "TARGETS": ("Experiment", "Segment"),
    "PRODUCED": ("Experiment", "CausalOutput"),
    "GENERATED": ("Experiment", "Learning"),
    "CONFIRMS": ("Learning", "Hypothesis"),
    "CONTRADICTS": ("Learning", "Hypothesis"),
    "APPLIES_TO": ("Learning", "Segment"),
    "APPLIES_TO_METRIC": ("Learning", "Metric"),
    "REPLICATES": ("Learning", "Learning"),
    "DETECTED_IN": ("Anomaly", "Experiment"),
    "AFFECTS": ("Anomaly", "Metric"),
    "OWNS": ("Owner", "Experiment"),
    "SIMILAR_TO": ("Experiment", "Experiment"),
    "CONCURRENT_WITH": ("Experiment", "Experiment"),
    "PRECEDED_BY": ("Experiment", "Experiment"),
}

DDL = """
CREATE TABLE IF NOT EXISTS kg_nodes (
    node_id    VARCHAR PRIMARY KEY,
    node_type  VARCHAR NOT NULL,
    properties JSON    NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kg_edges (
    edge_id    VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    edge_type  VARCHAR NOT NULL,
    source_id  VARCHAR NOT NULL,
    target_id  VARCHAR NOT NULL,
    weight     DOUBLE  DEFAULT 1.0,
    properties JSON    DEFAULT '{}',
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE (edge_type, source_id, target_id)
);

CREATE INDEX IF NOT EXISTS idx_kg_edges_source ON kg_edges (source_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_target ON kg_edges (target_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_type   ON kg_edges (edge_type);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_type   ON kg_nodes (node_type);
"""


# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE GRAPH
# ─────────────────────────────────────────────────────────────────────────────


class KnowledgeGraph:

    def __init__(self, db=None):
        if db is None:
            try:
                import duckdb

                db = duckdb.connect(":memory:")
            except ImportError:
                raise RuntimeError("duckdb is required for KnowledgeGraph. pip install duckdb")
        self._db = db
        self._initialise_schema()

    def _initialise_schema(self) -> None:
        try:
            self._db.execute(DDL)
        except Exception as e:
            logger.warning("KG schema init warning: %s", e)

    # ── Low-level node/edge operations ────────────────────────────────────────

    def upsert_node(self, node_type: str, node_id: str, properties: Dict[str, Any]) -> None:
        props_json = json.dumps(properties, default=str)
        try:
            self._db.execute(
                """
                INSERT INTO kg_nodes (node_id, node_type, properties, updated_at)
                VALUES (?, ?, ?, current_timestamp)
                ON CONFLICT (node_id) DO UPDATE SET
                    properties = excluded.properties,
                    updated_at = now()
            """,
                [node_id, node_type, props_json],
            )
        except Exception as e:
            logger.warning("upsert_node failed for %s %s: %s", node_type, node_id, e)

    def upsert_edge(
        self,
        edge_type: str,
        source_id: str,
        target_id: str,
        weight: float = 1.0,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        props_json = json.dumps(properties or {}, default=str)
        try:
            self._db.execute(
                """
                INSERT INTO kg_edges (edge_id, edge_type, source_id, target_id, weight, properties)
                VALUES (gen_random_uuid()::VARCHAR, ?, ?, ?, ?, ?)
                ON CONFLICT (edge_type, source_id, target_id) DO UPDATE SET
                    weight = excluded.weight,
                    properties = excluded.properties
            """,
                [edge_type, source_id, target_id, weight, props_json],
            )
        except Exception as e:
            logger.warning("upsert_edge failed %s %s→%s: %s", edge_type, source_id, target_id, e)

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        try:
            row = self._db.execute(
                "SELECT node_type, properties FROM kg_nodes WHERE node_id = ?", [node_id]
            ).fetchone()
            if row:
                return {"node_type": row[0], **json.loads(row[1])}
        except Exception as e:
            logger.warning("get_node failed for %s: %s", node_id, e)
        return None

    def get_neighbours(
        self,
        node_id: str,
        edge_type: Optional[str] = None,
        direction: str = "out",  # "out" | "in" | "both"
    ) -> List[Dict[str, Any]]:
        conditions = []
        params = []
        if direction in ("out", "both"):
            conditions.append("e.source_id = ?")
            params.append(node_id)
        if direction in ("in", "both"):
            conditions.append("e.target_id = ?")
            params.append(node_id)
        where = " OR ".join(f"({c})" for c in conditions)
        edge_filter = ""
        if edge_type:
            edge_filter = " AND e.edge_type = ?"
            params.append(edge_type)
        sql = f"""
            SELECT
                e.edge_type,
                e.source_id,
                e.target_id,
                e.weight,
                n_other.node_type,
                n_other.properties
            FROM kg_edges e
            JOIN kg_nodes n_other ON (
                CASE WHEN e.source_id = '{node_id}' THEN e.target_id ELSE e.source_id END
                = n_other.node_id
            )
            WHERE ({where}){edge_filter}
        """
        try:
            rows = self._db.execute(sql, params).fetchall()
            return [
                {
                    "edge_type": r[0],
                    "source_id": r[1],
                    "target_id": r[2],
                    "weight": r[3],
                    "node_type": r[4],
                    **json.loads(r[5]),
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("get_neighbours failed for %s: %s", node_id, e)
            return []

    # ── Domain-specific write operations ─────────────────────────────────────

    def record_experiment(self, experiment_id: str, props: Dict[str, Any]) -> None:
        self.upsert_node("Experiment", experiment_id, props)

    def record_experiment_result(
        self,
        result,  # ExperimentResult artifact
        causal_estimates: Optional[list] = None,
        violations: Optional[list] = None,
    ) -> None:
        # Experiment node
        self.upsert_node(
            "Experiment",
            result.experiment_id,
            {
                "name": result.experiment_name,
                "status": "completed",
                "primary_metric": result.primary_metric,
                "verdict": result.verdict.value,
                "ship": result.ship_recommendation.value,
                "n_total": result.n_total,
                "analysed_at": str(result.analysed_at),
            },
        )

        # Metric node + edge
        self.upsert_node("Metric", result.primary_metric, {"name": result.primary_metric})
        self.upsert_edge("MEASURES", result.experiment_id, result.primary_metric)

        # Causal estimate nodes + edges
        if causal_estimates:
            for est in causal_estimates:
                est_id = str(est.artifact_id)
                self.upsert_node(
                    "CausalOutput",
                    est_id,
                    {
                        "method": est.method,
                        "estimand": est.estimand,
                        "estimate": est.estimate,
                        "ci_lo": est.ci_lo,
                        "ci_hi": est.ci_hi,
                        "p_value": est.p_value,
                        "metric": est.outcome_metric,
                    },
                )
                self.upsert_edge("PRODUCED", result.experiment_id, est_id)

        # Guardrail violations
        if violations:
            for v in violations:
                v_id = str(v.artifact_id)
                self.upsert_node(
                    "Anomaly",
                    v_id,
                    {
                        "anomaly_type": "guardrail_violation",
                        "metric": v.metric_name,
                        "severity": v.severity,
                        "detected_at": str(v.detected_at),
                        "resolved": False,
                    },
                )
                self.upsert_edge("DETECTED_IN", v_id, result.experiment_id)
                self.upsert_edge("AFFECTS", v_id, v.metric_name)

        # Learnings
        for learning in result.learnings:
            l_id = learning.get("id", str(uuid4()))
            self.upsert_node("Learning", l_id, learning)
            self.upsert_edge("GENERATED", result.experiment_id, l_id)

    def record_anomaly(self, anomaly) -> None:
        a_id = str(anomaly.artifact_id)
        self.upsert_node(
            "Anomaly",
            a_id,
            {
                "anomaly_type": anomaly.anomaly_type,
                "metric": anomaly.metric_affected,
                "severity": anomaly.severity.value,
                "detected_at": str(anomaly.detected_at),
                "resolved": anomaly.resolved,
            },
        )
        for exp_id in anomaly.experiment_ids_concurrent:
            self.upsert_edge("DETECTED_IN", a_id, exp_id)

    # ── Domain-specific query operations ─────────────────────────────────────

    def find_similar_experiments(
        self,
        experiment_id: str,
        top_k: int = 5,
        match_on: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        node = self.get_node(experiment_id)
        if not node:
            return []
        metric = node.get("primary_metric", "")
        feature_area = node.get("feature_area", "")

        try:
            rows = self._db.execute(
                """
                SELECT n.node_id, n.properties
                FROM kg_nodes n
                WHERE n.node_type = 'Experiment'
                  AND n.node_id != ?
                  AND (
                      json_extract_string(n.properties, '$.primary_metric') = ?
                      OR json_extract_string(n.properties, '$.feature_area')  = ?
                  )
                ORDER BY n.updated_at DESC
                LIMIT ?
            """,
                [experiment_id, metric, feature_area, top_k],
            ).fetchall()
            return [{"experiment_id": r[0], **json.loads(r[1])} for r in rows]
        except Exception as e:
            logger.warning("find_similar_experiments failed: %s", e)
            return []

    def get_learnings_for_context(
        self,
        metric: Optional[str] = None,
        domain: Optional[str] = None,
        min_confidence: str = "tentative",
    ) -> List[Dict[str, Any]]:
        confidence_rank = {"confirmed": 3, "probable": 2, "tentative": 1}
        min_rank = confidence_rank.get(min_confidence, 1)
        try:
            rows = self._db.execute(
                """
                SELECT node_id, properties
                FROM kg_nodes
                WHERE node_type = 'Learning'
                ORDER BY updated_at DESC
                LIMIT 50
            """
            ).fetchall()
            learnings = []
            for row in rows:
                props = json.loads(row[1])
                conf = props.get("confidence", "tentative")
                rank = confidence_rank.get(conf, 1)
                if rank < min_rank:
                    continue
                metrics = props.get("applicable_metrics", [])
                ldom = props.get("domain", "")
                if metric and metric not in metrics:
                    continue
                if domain and domain != ldom:
                    continue
                learnings.append({"learning_id": row[0], **props})
            return learnings
        except Exception as e:
            logger.warning("get_learnings_for_context failed: %s", e)
            return []

    def detect_concurrent_experiments(
        self,
        experiment_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[str]:
        try:
            rows = self._db.execute(
                """
                SELECT source_id FROM kg_edges
                WHERE edge_type = 'CONCURRENT_WITH' AND target_id = ?
                UNION
                SELECT target_id FROM kg_edges
                WHERE edge_type = 'CONCURRENT_WITH' AND source_id = ?
            """,
                [experiment_id, experiment_id],
            ).fetchall()
            return [r[0] for r in rows]
        except Exception as e:
            logger.warning("detect_concurrent_experiments failed: %s", e)
            return []

    def trace_root_cause(self, anomaly_id: str) -> List[Dict[str, Any]]:
        chain = []
        try:
            # Level 1: experiments where anomaly was detected
            exp_rows = self._db.execute(
                """
                SELECT target_id FROM kg_edges
                WHERE edge_type = 'DETECTED_IN' AND source_id = ?
            """,
                [anomaly_id],
            ).fetchall()
            for (exp_id,) in exp_rows:
                exp_node = self.get_node(exp_id)
                chain.append({"level": 1, "type": "Experiment", "id": exp_id, "props": exp_node})

                # Level 2: causal outputs from those experiments
                co_rows = self._db.execute(
                    """
                    SELECT target_id FROM kg_edges
                    WHERE edge_type = 'PRODUCED' AND source_id = ?
                """,
                    [exp_id],
                ).fetchall()
                for (co_id,) in co_rows:
                    co_node = self.get_node(co_id)
                    chain.append(
                        {"level": 2, "type": "CausalOutput", "id": co_id, "props": co_node}
                    )

                # Level 3: learnings from those experiments
                l_rows = self._db.execute(
                    """
                    SELECT target_id FROM kg_edges
                    WHERE edge_type = 'GENERATED' AND source_id = ?
                """,
                    [exp_id],
                ).fetchall()
                for (l_id,) in l_rows:
                    l_node = self.get_node(l_id)
                    chain.append({"level": 3, "type": "Learning", "id": l_id, "props": l_node})
        except Exception as e:
            logger.warning("trace_root_cause failed for %s: %s", anomaly_id, e)
        return chain

    def get_graph_summary(self) -> Dict[str, int]:
        summary = {}
        try:
            node_counts = self._db.execute(
                """
                SELECT node_type, COUNT(*) FROM kg_nodes GROUP BY node_type
            """
            ).fetchall()
            for node_type, count in node_counts:
                summary[f"nodes_{node_type}"] = count

            edge_counts = self._db.execute(
                """
                SELECT edge_type, COUNT(*) FROM kg_edges GROUP BY edge_type
            """
            ).fetchall()
            for edge_type, count in edge_counts:
                summary[f"edges_{edge_type}"] = count
        except Exception as e:
            logger.warning("get_graph_summary failed: %s", e)
        return summary

    def search_by_domain(self, domain: str, node_type: str = "Learning") -> List[Dict]:
        try:
            rows = self._db.execute(
                """
                SELECT node_id, properties FROM kg_nodes
                WHERE node_type = ?
                  AND json_extract_string(properties, '$.domain') = ?
                ORDER BY updated_at DESC
            """,
                [node_type, domain],
            ).fetchall()
            return [{"id": r[0], **json.loads(r[1])} for r in rows]
        except Exception as e:
            logger.warning("search_by_domain failed: %s", e)
            return []


__all__ = [
    "KnowledgeGraph",
    "NODE_TYPES",
    "EDGE_TYPES",
]
