from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from continum.paths import RUNTIME_DATA_DIR, ensure_runtime_data_dir

logger = logging.getLogger("continum.ContextGraph.session")

ensure_runtime_data_dir()
SESSION_FILE = os.path.join(RUNTIME_DATA_DIR, "continum_session.json")


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ExecutionRecord:
    run_id: str
    module: str
    phase: str
    started_at: str
    elapsed_s: float = 0.0
    ok: bool = True
    error: str = ""
    summary: str = ""
    outputs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: Dict) -> "ExecutionRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Recommendation:
    source: str
    action: str  # e.g. "Run Planning", "Generate Guardrails"
    reason: str
    module_key: str  # key into dispatcher registry
    priority: int = 1  # 1=high, 2=medium, 3=low
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return self.__dict__.copy()


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT SESSION
# ─────────────────────────────────────────────────────────────────────────────


class ExperimentSession:

    def __init__(self, session_id: Optional[str] = None, client_name: str = "demo"):
        self.session_id: str = session_id or str(uuid4())[:8]
        self.client_name: str = client_name
        self.created_at: str = datetime.utcnow().isoformat()
        self.last_active: str = self.created_at
        self.mode: str = "synthetic"

        # Runtime objects (not JSON-serialised)
        self.db: Any = None
        self.state: Any = None
        self.datasets: Dict[str, Any] = {}

        # Persistent metadata
        self.semantic_mappings: Dict[str, str] = {}
        self.active_metrics: List[str] = []
        self.experiment_configs: Dict[str, Any] = {}
        self.execution_history: List[ExecutionRecord] = []
        self.recommendations: List[Recommendation] = []
        self.active_experiment: Optional[str] = None
        # None = no dataset/company selected yet (gates dataset-level chat).
        self.active_dataset: Optional[str] = None

        # KV store for cross-module data sharing
        self._context: Dict[str, Any] = {}

    # ── Context store ──────────────────────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        self._context[key] = value
        self._touch()

    def get(self, key: str, default: Any = None) -> Any:
        return self._context.get(key, default)

    def has(self, key: str) -> bool:
        return key in self._context

    # ── Execution tracking ─────────────────────────────────────────────────────

    def record_run(
        self,
        module: str,
        phase: str,
        elapsed_s: float,
        ok: bool = True,
        error: str = "",
        summary: str = "",
        outputs: Optional[Dict] = None,
    ) -> ExecutionRecord:
        rec = ExecutionRecord(
            run_id=str(uuid4())[:8],
            module=module,
            phase=phase,
            started_at=datetime.utcnow().isoformat(),
            elapsed_s=round(elapsed_s, 3),
            ok=ok,
            error=error,
            summary=summary,
            outputs=outputs or {},
        )
        self.execution_history.append(rec)
        self._touch()
        return rec

    def last_run(self, module: Optional[str] = None) -> Optional[ExecutionRecord]:
        history = [r for r in self.execution_history if module is None or r.module == module]
        return history[-1] if history else None

    # ── Recommendations ────────────────────────────────────────────────────────

    def add_recommendation(
        self, source: str, action: str, reason: str, module_key: str, priority: int = 1
    ) -> None:
        # Deduplicate by module_key
        self.recommendations = [r for r in self.recommendations if r.module_key != module_key]
        self.recommendations.append(
            Recommendation(
                source=source,
                action=action,
                reason=reason,
                module_key=module_key,
                priority=priority,
            )
        )
        self.recommendations.sort(key=lambda r: r.priority)
        self._touch()

    def clear_recommendations(self) -> None:
        self.recommendations = []

    # ── Active experiment ──────────────────────────────────────────────────────

    def select_experiment(self, name: str) -> None:
        self.active_experiment = name
        self._touch()
        logger.info("Session %s: active experiment → %s", self.session_id, name)

    def select_dataset(self, name: Optional[str]) -> None:
        """Set (or clear, with a falsy name) the active dataset/company. Clearing
        the dataset also drops the active experiment, since experiments are scoped
        to a dataset."""
        self.active_dataset = name or None
        if not self.active_dataset:
            self.active_experiment = None
        self._touch()
        logger.info("Session %s: active dataset → %s", self.session_id, self.active_dataset)

    # ── Metrics ────────────────────────────────────────────────────────────────

    def set_metrics(self, metrics: List[str]) -> None:
        self.active_metrics = list(dict.fromkeys(metrics))  # dedup preserving order
        self._touch()

    # ── Serialisation ──────────────────────────────────────────────────────────

    def _touch(self) -> None:
        self.last_active = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict:
        d = {
            "session_id": self.session_id,
            "client_name": self.client_name,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "mode": self.mode,
            "semantic_mappings": self.semantic_mappings,
            "active_metrics": self.active_metrics,
            "experiment_configs": self.experiment_configs,
            "active_experiment": self.active_experiment,
            "active_dataset": self.active_dataset,
            "execution_history": [r.to_dict() for r in self.execution_history],
            "recommendations": [r.to_dict() for r in self.recommendations],
            "context_keys": list(self._context.keys()),
        }
        # Include fork metadata if present
        if hasattr(self, "_parent_id"):
            d["_parent_id"] = self._parent_id
            d["_parent_snapshot"] = getattr(self, "_parent_snapshot", [])
            d["fork_description"] = getattr(self, "fork_description", "")
        return d

    def save(self, path: str = SESSION_FILE) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, default=str)
            logger.debug("Session %s saved → %s", self.session_id, path)
        except Exception as e:
            logger.warning("Could not save session: %s", e)

    @classmethod
    def load(cls, path: str = SESSION_FILE, client_name: str = "demo") -> "ExperimentSession":
        if not os.path.exists(path):
            return cls(client_name=client_name)
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            session = cls(
                session_id=d.get("session_id"), client_name=d.get("client_name", client_name)
            )
            session.created_at = d.get("created_at", session.created_at)
            session.last_active = d.get("last_active", session.last_active)
            session.mode = d.get("mode", "synthetic")
            session.semantic_mappings = d.get("semantic_mappings", {})
            session.active_metrics = d.get("active_metrics", [])
            session.experiment_configs = d.get("experiment_configs", {})
            session.active_experiment = d.get("active_experiment")
            session.active_dataset = d.get("active_dataset")
            session.execution_history = [
                ExecutionRecord.from_dict(r) for r in d.get("execution_history", [])
            ]
            session.recommendations = [Recommendation(**r) for r in d.get("recommendations", [])]
            logger.info(
                "Session %s loaded from %s (%d runs)",
                session.session_id,
                path,
                len(session.execution_history),
            )
            return session
        except Exception as e:
            logger.warning("Could not load session from %s: %s — starting fresh", path, e)
            return cls(client_name=client_name)

    # ── Session Forking + Branching ────────────────────────────────────────────

    def fork(self, label: Optional[str] = None) -> "ExperimentSession":
        import copy

        fork = ExperimentSession(client_name=self.client_name)
        fork.mode = self.mode
        fork.semantic_mappings = copy.deepcopy(self.semantic_mappings)
        fork.active_metrics = list(self.active_metrics)
        fork.experiment_configs = copy.deepcopy(self.experiment_configs)
        fork.active_experiment = self.active_experiment
        fork.active_dataset = self.active_dataset
        fork._context = copy.deepcopy(self._context)
        fork._parent_id = self.session_id
        fork._parent_snapshot = [r.to_dict() for r in self.execution_history]
        fork.fork_description = (
            label or f"Fork of {self.session_id} at run #{len(self.execution_history)}"
        )

        # Save the parent so it's not lost
        self.save()
        fork_path = os.path.join(RUNTIME_DATA_DIR, f"continum_fork_{fork.session_id}.json")
        fork.save(path=fork_path)
        logger.info("Session %s forked → %s", self.session_id, fork.session_id)
        return fork

    def list_forks(self) -> List[str]:
        import glob

        forks = []
        pattern = os.path.join(RUNTIME_DATA_DIR, "continum_fork_*.json")
        for path in glob.glob(pattern):
            try:
                import json as _j

                with open(path) as f:
                    d = _j.load(f)
                if d.get("_parent_id") == self.session_id:
                    forks.append(d["session_id"])
            except Exception:
                pass
        return forks

    def summary_line(self) -> str:
        n_runs = len(self.execution_history)
        exp = self.active_experiment or "—"
        mets = ", ".join(self.active_metrics[:3]) or "—"
        return (
            f"Session {self.session_id} | {self.client_name} | "
            f"Experiment: {exp} | Metrics: {mets} | Runs: {n_runs}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SESSION SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

_ACTIVE_SESSION: Optional[ExperimentSession] = None


def get_session() -> ExperimentSession:
    global _ACTIVE_SESSION
    if _ACTIVE_SESSION is None:
        _ACTIVE_SESSION = ExperimentSession.load()
    return _ACTIVE_SESSION


def new_session(client_name: str = "demo") -> ExperimentSession:
    global _ACTIVE_SESSION
    _ACTIVE_SESSION = ExperimentSession(client_name=client_name)
    return _ACTIVE_SESSION


def set_session(session: ExperimentSession) -> None:
    global _ACTIVE_SESSION
    _ACTIVE_SESSION = session


__all__ = [
    "ExperimentSession",
    "ExecutionRecord",
    "Recommendation",
    "get_session",
    "new_session",
    "set_session",
    "SESSION_FILE",
]
