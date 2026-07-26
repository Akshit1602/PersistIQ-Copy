from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from continum.paths import RUNTIME_DATA_DIR, ensure_runtime_data_dir

logger = logging.getLogger("continum.memory")


class ExecutionMemory:
    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._job_runs: Dict[str, Dict] = {}
        self._cache: Dict[str, Any] = {}
        self._retries: Dict[str, List] = {}
        self._baselines: Dict[str, float] = {}

    def record_job_start(self, job_id: str, dag_name: str, params: Optional[Dict] = None) -> None:
        self._job_runs[job_id] = {
            "dag_name": dag_name,
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "params": params or {},
        }

    def record_job_complete(self, job_id: str, outputs: Optional[Dict] = None) -> None:
        if job_id in self._job_runs:
            self._job_runs[job_id].update(
                {
                    "status": "completed",
                    "completed_at": datetime.utcnow().isoformat(),
                    "outputs": outputs or {},
                }
            )

    def record_job_failed(self, job_id: str, error: str) -> None:
        if job_id in self._job_runs:
            self._job_runs[job_id].update(
                {
                    "status": "failed",
                    "failed_at": datetime.utcnow().isoformat(),
                    "error": error,
                }
            )

    def get_job_status(self, job_id: str) -> Optional[Dict]:
        return self._job_runs.get(job_id)

    def get_last_run(self, dag_name: str) -> Optional[str]:
        runs = [
            r
            for r in self._job_runs.values()
            if r.get("dag_name") == dag_name and r.get("status") == "completed"
        ]
        if not runs:
            return None
        return max(runs, key=lambda r: r.get("completed_at", ""))["completed_at"]

    def set_cache(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        self._cache[key] = {
            "value": value,
            "expires_at": datetime.utcnow().timestamp() + ttl_seconds,
        }

    def get_cache(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if datetime.utcnow().timestamp() > entry["expires_at"]:
            del self._cache[key]
            return None
        return entry["value"]

    def invalidate_cache(self, key: str) -> None:
        self._cache.pop(key, None)

    def record_retry(self, task_id: str, attempt: int, error: str) -> None:
        self._retries.setdefault(task_id, []).append(
            {
                "attempt": attempt,
                "error": error,
                "at": datetime.utcnow().isoformat(),
            }
        )

    def get_retry_count(self, task_id: str) -> int:
        return len(self._retries.get(task_id, []))

    def set_pipeline_baseline(self, metric: str, value: float) -> None:
        self._baselines[metric] = value

    def get_pipeline_baseline(self, metric: str) -> Optional[float]:
        return self._baselines.get(metric)

    def set_bootstrap_state(self, mode: str, timestamp: str) -> None:
        self._store["bootstrap_mode"] = mode
        self._store["bootstrap_timestamp"] = timestamp

    def get_bootstrap_mode(self) -> str:
        return self._store.get("bootstrap_mode", "csv")

    def is_production_ready(self) -> bool:
        return self.get_bootstrap_mode() == "production_ready"

    def set_last_health_check(self, result: str) -> None:
        self._store["last_health_check"] = datetime.utcnow().isoformat()
        self._store["last_health_check_result"] = result

    def get_last_health_check(self) -> Optional[str]:
        return self._store.get("last_health_check")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "store": self._store,
            "job_runs": self._job_runs,
            "retries": self._retries,
            "baselines": self._baselines,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionMemory":
        em = cls()
        em._store = data.get("store", {})
        em._job_runs = data.get("job_runs", {})
        em._retries = data.get("retries", {})
        em._baselines = data.get("baselines", {})
        return em


class OrganisationalMemory:
    def __init__(self, knowledge_graph=None):
        if knowledge_graph is None:
            from continum.ContextGraph.knowledge_graph import KnowledgeGraph

            knowledge_graph = KnowledgeGraph()
        self._kg = knowledge_graph
        self._client_config: Dict[str, Any] = {}
        self._dimension_config: Dict[str, Any] = {}
        self._approved_schemas: List[Dict] = []

    def set_client_config(
        self,
        client_name: str,
        schema_version: int,
        column_map: Dict,
        segment_map: Dict,
        platform_map: Dict,
        approved_by: str,
    ) -> None:
        config = {
            "client_name": client_name,
            "schema_version": schema_version,
            "column_map": column_map,
            "segment_map": segment_map,
            "platform_map": platform_map,
            "approved_by": approved_by,
            "approved_at": datetime.utcnow().isoformat(),
        }
        self._client_config = config
        self._approved_schemas.append(config)

    def get_client_config(self) -> Dict[str, Any]:
        return dict(self._client_config)

    def get_client_name(self) -> str:
        return self._client_config.get("client_name", "unknown")

    def set_dimension_config(self, config: Dict[str, Any]) -> None:
        self._dimension_config = {**config, "set_at": datetime.utcnow().isoformat()}

    def get_analysis_dimensions(self) -> List[str]:
        return self._dimension_config.get(
            "analysis_dimensions", ["account_segment", "platform", "category", "country"]
        )

    def get_segments(self) -> List[str]:
        return self._dimension_config.get(
            "segments", ["Individuals", "Core", "Growth", "Enterprise"]
        )

    def get_platforms(self) -> List[str]:
        return self._dimension_config.get("platforms", ["web", "mobile"])

    def store_learning(
        self,
        statement: str,
        domain: str,
        experiment_ids: List[str],
        confidence: str = "tentative",
        evidence_type: str = "correlational",
        applicable_metrics: Optional[List[str]] = None,
        applicable_segments: Optional[List[str]] = None,
        owner: str = "",
    ) -> str:
        from uuid import uuid4

        learning_id = str(uuid4())
        self._kg.upsert_node(
            "Learning",
            learning_id,
            {
                "statement": statement,
                "domain": domain,
                "confidence": confidence,
                "evidence_type": evidence_type,
                "applicable_metrics": applicable_metrics or [],
                "applicable_segments": applicable_segments or [],
                "experiment_ids": experiment_ids,
                "owner": owner,
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        for exp_id in experiment_ids:
            self._kg.upsert_edge("GENERATED", exp_id, learning_id)
        return learning_id

    def get_relevant_learnings(
        self,
        metric: Optional[str] = None,
        domain: Optional[str] = None,
        min_confidence: str = "tentative",
    ) -> List[Dict]:
        return self._kg.get_learnings_for_context(
            metric=metric, domain=domain, min_confidence=min_confidence
        )

    def register_experiment(self, experiment_id: str, props: Dict[str, Any]) -> None:
        self._kg.record_experiment(experiment_id, props)

    def get_similar_experiments(self, experiment_id: str, top_k: int = 5) -> List[Dict]:
        return self._kg.find_similar_experiments(experiment_id, top_k=top_k)

    def get_domain_learnings(self, domain: str) -> List[Dict]:
        return self._kg.search_by_domain(domain, "Learning")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_config": self._client_config,
            "dimension_config": self._dimension_config,
            "graph_summary": self._kg.get_graph_summary(),
        }


class ContinumState:

    def __init__(self, knowledge_graph=None):
        self.execution = ExecutionMemory()
        self.org = OrganisationalMemory(knowledge_graph)

    def save_to_file(self, path: Optional[str] = None) -> None:
        if path is None:
            ensure_runtime_data_dir()
            path = os.path.join(RUNTIME_DATA_DIR, "continum_state.json")
        data = {
            "execution": self.execution.to_dict(),
            "org_config": {
                "client_config": self.org.get_client_config(),
                "dimension_config": self.org._dimension_config,
            },
            "saved_at": datetime.utcnow().isoformat(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def load_from_file(cls, path: Optional[str] = None, knowledge_graph=None) -> "ContinumState":
        import os

        if path is None:
            path = os.path.join(RUNTIME_DATA_DIR, "continum_state.json")
        state = cls(knowledge_graph)
        if not os.path.exists(path):
            return state
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            state.execution = ExecutionMemory.from_dict(data.get("execution", {}))
            org_cfg = data.get("org_config", {})
            if org_cfg.get("client_config"):
                cc = org_cfg["client_config"]
                state.org.set_client_config(
                    client_name=cc.get("client_name", ""),
                    schema_version=cc.get("schema_version", 1),
                    column_map=cc.get("column_map", {}),
                    segment_map=cc.get("segment_map", {}),
                    platform_map=cc.get("platform_map", {}),
                    approved_by=cc.get("approved_by", ""),
                )
            if org_cfg.get("dimension_config"):
                state.org.set_dimension_config(org_cfg["dimension_config"])
        except Exception as e:
            logger.warning("Could not load state from %s: %s", path, e)
        return state

    @property
    def mode(self) -> str:
        return self.execution.get_bootstrap_mode()

    def is_production_ready(self) -> bool:
        return self.execution.is_production_ready()

    def reset(self) -> None:
        self.execution = ExecutionMemory()


__all__ = ["ExecutionMemory", "OrganisationalMemory", "ContinumState"]
