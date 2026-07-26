from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from continum.paths import RUNTIME_DATA_DIR, ensure_runtime_data_dir

logger = logging.getLogger("continum.orchestration.engine")


# ─────────────────────────────────────────────────────────────────────────────
# LINEAGE RECORD
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LineageRecord:
    run_id: str
    experiment_id: str
    experiment_name: str
    analyst: str
    started_at: str  # ISO 8601
    finished_at: str  # ISO 8601
    elapsed_s: float
    status: str  # "completed" | "failed" | "partial"
    task_results: Tuple[Dict, ...]  # serialised TaskResult per task
    n_tasks_ok: int
    n_tasks_failed: int
    verdict: Optional[str] = None
    recommendation: Optional[str] = None
    primary_metric: Optional[Dict] = None
    input_hash: Optional[str] = None
    host: str = ""
    continum_version: str = "0.3.0"


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTION REGISTRY (append-only NDJSON lineage log; read by CLI replay + /api/lineage)
# ─────────────────────────────────────────────────────────────────────────────


class ExecutionRegistry:

    def __init__(self, registry_path: Optional[str] = None):
        if registry_path is None:
            ensure_runtime_data_dir()
            registry_path = os.path.join(RUNTIME_DATA_DIR, ".continum_registry.ndjson")
        self.path = Path(registry_path)

    def append(self, record: LineageRecord) -> None:
        try:
            payload = json.dumps(asdict(record), default=str)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(payload + "\n")
            logger.info("LineageRecord written: run_id=%s status=%s", record.run_id, record.status)
        except Exception as e:
            logger.error("ExecutionRegistry write failed: %s", e)

    def read_all(self) -> List[Dict]:
        if not self.path.exists():
            return []
        records = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        except Exception as e:
            logger.warning("ExecutionRegistry read failed: %s", e)
        return records

    def read_for_experiment(self, experiment_id: str) -> List[Dict]:
        return [r for r in self.read_all() if r.get("experiment_id") == experiment_id]

    def latest_run(self, experiment_id: str) -> Optional[Dict]:
        runs = self.read_for_experiment(experiment_id)
        return runs[-1] if runs else None


__all__ = [
    "LineageRecord",
    "ExecutionRegistry",
]
