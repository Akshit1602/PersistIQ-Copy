from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import time
import traceback
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from continum.runtime.config import RUNTIME_DATA_DIR, ensure_runtime_data_dir

logger = logging.getLogger("continum.orchestration.engine")


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ExecutionContext:
    run_id:         str
    experiment_id:  str
    experiment_name: str
    analyst:        str     = "system"
    alpha:          float   = 0.05
    control_variant: str    = "control"
    output_dir:     str     = "."
    dry_run:        bool    = False
    seed:           int     = 42
    tags:           Tuple   = field(default_factory=tuple)

    def with_update(self, **kwargs) -> "ExecutionContext":
        d = {f: getattr(self, f) for f in self.__dataclass_fields__}
        d.update(kwargs)
        return ExecutionContext(**d)


@dataclass
class TaskResult:
    task_name:      str
    ok:             bool
    value:          Any           = None
    error:          Optional[str] = None
    traceback_str:  Optional[str] = None
    started_at:     Optional[datetime] = None
    finished_at:    Optional[datetime] = None
    elapsed_s:      float         = 0.0
    n_retries:      int           = 0
    input_hash:     Optional[str] = None
    output_hash:    Optional[str] = None
    metadata:       Dict          = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        return int(self.elapsed_s * 1000)


@dataclass(frozen=True)
class LineageRecord:
    run_id:           str
    experiment_id:    str
    experiment_name:  str
    analyst:          str
    started_at:       str          # ISO 8601
    finished_at:      str          # ISO 8601
    elapsed_s:        float
    status:           str          # "completed" | "failed" | "partial"
    task_results:     Tuple[Dict, ...]   # serialised TaskResult per task
    n_tasks_ok:       int
    n_tasks_failed:   int
    verdict:          Optional[str] = None
    recommendation:   Optional[str] = None
    primary_metric:   Optional[Dict] = None
    input_hash:       Optional[str] = None
    host:             str  = ""
    continum_version: str  = "0.3.0"


# ─────────────────────────────────────────────────────────────────────────────
# CHECKPOINT STORE
# ─────────────────────────────────────────────────────────────────────────────

class CheckpointStore:

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            ensure_runtime_data_dir()
            base_dir = os.path.join(RUNTIME_DATA_DIR, ".continum_checkpoints")
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str, task_name: str) -> Path:
        run_dir = self.base_dir / run_id
        run_dir.mkdir(exist_ok=True)
        return run_dir / f"{task_name}.json"

    def save(self, run_id: str, task_name: str, result: TaskResult) -> None:
        p = self._path(run_id, task_name)
        payload = {
            "task_name":     result.task_name,
            "ok":            result.ok,
            "error":         result.error,
            "elapsed_s":     result.elapsed_s,
            "n_retries":     result.n_retries,
            "input_hash":    result.input_hash,
            "output_hash":   result.output_hash,
            "started_at":    result.started_at.isoformat() if result.started_at else None,
            "finished_at":   result.finished_at.isoformat() if result.finished_at else None,
            "metadata":      result.metadata,
            # value is NOT serialised (can be any Python object) — only metadata
        }
        try:
            p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            logger.debug("Checkpoint saved: %s/%s", run_id, task_name)
        except Exception as e:
            logger.warning("Checkpoint save failed for %s/%s: %s", run_id, task_name, e)

    def load(self, run_id: str, task_name: str) -> Optional[Dict]:
        p = self._path(run_id, task_name)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def exists(self, run_id: str, task_name: str) -> bool:
        return self._path(run_id, task_name).exists()

    def list_completed(self, run_id: str) -> List[str]:
        run_dir = self.base_dir / run_id
        if not run_dir.exists():
            return []
        return [p.stem for p in run_dir.glob("*.json")]

    def clear(self, run_id: str) -> None:
        import shutil
        run_dir = self.base_dir / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTION REGISTRY
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
            logger.info("LineageRecord written: run_id=%s status=%s",
                        record.run_id, record.status)
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


# ─────────────────────────────────────────────────────────────────────────────
# RETRY POLICY
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RetryPolicy:
    max_attempts:      int   = 3
    backoff_seconds:   float = 1.0
    backoff_multiplier: float = 2.0
    retryable_errors:  Tuple = field(default_factory=lambda: (Exception,))
    abort_on_error:    bool  = False   # if True, pipeline stops on first failure


# ─────────────────────────────────────────────────────────────────────────────
# INPUT HASHING
# ─────────────────────────────────────────────────────────────────────────────

def _hash_input(obj: Any) -> str:
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            return hashlib.sha256(
                pd.util.hash_pandas_object(obj, index=True).values.tobytes()
            ).hexdigest()[:12]
    except Exception:
        pass
    try:
        s = json.dumps(obj, sort_keys=True, default=str)
        return hashlib.sha256(s.encode()).hexdigest()[:12]
    except Exception:
        return hashlib.sha256(str(obj).encode()).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE EXECUTOR
# ─────────────────────────────────────────────────────────────────────────────

class PipelineExecutor:

    def __init__(
        self,
        ctx:        ExecutionContext,
        checkpoints: Optional[CheckpointStore]   = None,
        registry:    Optional[ExecutionRegistry]  = None,
        resume:      bool = False,
    ):
        self.ctx         = ctx
        self.checkpoints = checkpoints or CheckpointStore()
        self.registry    = registry    or ExecutionRegistry()
        self.resume      = resume
        self._results:   Dict[str, TaskResult] = {}

    def run(
        self,
        tasks: List[Tuple[str, Callable, Any, Optional[RetryPolicy]]],
    ) -> Dict[str, TaskResult]:
        pipeline_start = datetime.now(timezone.utc)

        for task_name, fn, input_data, retry_policy in tasks:
            retry_policy = retry_policy or RetryPolicy()

            # Resume: skip if checkpoint exists and resume=True
            if self.resume and self.checkpoints.exists(self.ctx.run_id, task_name):
                ck = self.checkpoints.load(self.ctx.run_id, task_name)
                logger.info("[SKIP] %s — checkpoint found (resume mode)", task_name)
                self._results[task_name] = TaskResult(
                    task_name=task_name, ok=bool(ck and ck.get("ok")),
                    metadata={"resumed": True, **(ck or {})},
                )
                continue

            result = self._run_with_retry(task_name, fn, input_data, retry_policy)
            self._results[task_name] = result
            self.checkpoints.save(self.ctx.run_id, task_name, result)

            if not result.ok and retry_policy.abort_on_error:
                logger.error("[ABORT] %s failed and abort_on_error=True", task_name)
                break

        # Write lineage record
        self._write_lineage(pipeline_start)
        return self._results

    def _run_with_retry(
        self,
        task_name:    str,
        fn:           Callable,
        input_data:   Any,
        policy:       RetryPolicy,
    ) -> TaskResult:
        input_hash = _hash_input(input_data)
        attempt    = 0
        delay      = policy.backoff_seconds
        last_error = None
        last_tb    = None

        while attempt < policy.max_attempts:
            attempt += 1
            started = datetime.now(timezone.utc)
            t0      = time.perf_counter()
            try:
                if self.ctx.dry_run:
                    logger.info("[DRY-RUN] %s skipped", task_name)
                    return TaskResult(
                        task_name=task_name, ok=True, value=None,
                        started_at=started, finished_at=started,
                        elapsed_s=0.0, metadata={"dry_run": True},
                    )

                value    = fn(input_data, ctx=self.ctx) \
                           if _accepts_ctx(fn) else fn(input_data)
                elapsed  = time.perf_counter() - t0
                finished = datetime.now(timezone.utc)

                logger.info("[TASK] %-24s OK (%.2fs, attempt %d/%d)",
                            task_name, elapsed, attempt, policy.max_attempts)
                return TaskResult(
                    task_name=task_name, ok=True, value=value,
                    started_at=started, finished_at=finished,
                    elapsed_s=elapsed, n_retries=attempt - 1,
                    input_hash=input_hash,
                    output_hash=_hash_input(value),
                )

            except tuple(policy.retryable_errors) as e:
                elapsed    = time.perf_counter() - t0
                last_error = str(e)
                last_tb    = traceback.format_exc()
                logger.warning("[TASK] %-24s attempt %d/%d failed: %s",
                               task_name, attempt, policy.max_attempts, e)
                if attempt < policy.max_attempts:
                    time.sleep(delay)
                    delay *= policy.backoff_multiplier

        logger.error("[TASK] %-24s FAILED after %d attempts", task_name, attempt)
        return TaskResult(
            task_name=task_name, ok=False, value=None,
            error=last_error, traceback_str=last_tb,
            n_retries=attempt - 1,
            input_hash=input_hash,
        )

    def _write_lineage(self, pipeline_start: datetime) -> None:
        pipeline_end = datetime.now(timezone.utc)
        n_ok     = sum(1 for r in self._results.values() if r.ok)
        n_failed = sum(1 for r in self._results.values() if not r.ok)
        status   = ("completed" if n_failed == 0
                    else "failed" if n_ok == 0
                    else "partial")

        # Extract primary metric summary if available
        primary = None
        if "primary_analysis" in self._results and self._results["primary_analysis"].ok:
            val = self._results["primary_analysis"].value
            if hasattr(val, "primary_delta"):
                d = val.primary_delta
                primary = {
                    "metric":    d.metric_name,
                    "delta_pp":  round(d.delta_pp, 4),
                    "p_value":   round(d.p_value, 6),
                    "significant": d.is_significant,
                }

        record = LineageRecord(
            run_id=self.ctx.run_id,
            experiment_id=self.ctx.experiment_id,
            experiment_name=self.ctx.experiment_name,
            analyst=self.ctx.analyst,
            started_at=pipeline_start.isoformat(),
            finished_at=pipeline_end.isoformat(),
            elapsed_s=round((pipeline_end - pipeline_start).total_seconds(), 3),
            status=status,
            task_results=tuple(
                {
                    "task":      r.task_name,
                    "ok":        r.ok,
                    "elapsed_s": round(r.elapsed_s, 3),
                    "n_retries": r.n_retries,
                    "error":     r.error,
                    "input_hash": r.input_hash,
                    "output_hash": r.output_hash,
                }
                for r in self._results.values()
            ),
            n_tasks_ok=n_ok,
            n_tasks_failed=n_failed,
            primary_metric=primary,
            host=os.uname().nodename if hasattr(os, "uname") else "unknown",
        )
        self.registry.append(record)


def _accepts_ctx(fn: Callable) -> bool:
    import inspect
    try:
        sig = inspect.signature(fn)
        return "ctx" in sig.parameters
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY / CONVENIENCE
# ─────────────────────────────────────────────────────────────────────────────

def make_context(
    experiment_id:   str,
    experiment_name: str = "",
    analyst:         str = "system",
    alpha:           float = 0.05,
    control_variant: str = "control",
    output_dir:      str = ".",
    dry_run:         bool = False,
    seed:            int = 42,
) -> ExecutionContext:
    return ExecutionContext(
        run_id=uuid.uuid4().hex[:12],
        experiment_id=experiment_id,
        experiment_name=experiment_name or experiment_id,
        analyst=analyst,
        alpha=alpha,
        control_variant=control_variant,
        output_dir=output_dir,
        dry_run=dry_run,
        seed=seed,
    )


def task(
    name:         str,
    retry_policy: Optional[RetryPolicy] = None,
    abort_on_fail: bool = False,
):
    def decorator(fn: Callable) -> Callable:
        fn._task_name     = name
        fn._retry_policy  = retry_policy or RetryPolicy(abort_on_error=abort_on_fail)
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        wrapper._task_name    = name
        wrapper._retry_policy = fn._retry_policy
        return wrapper
    return decorator


__all__ = [
    "ExecutionContext",
    "TaskResult",
    "LineageRecord",
    "CheckpointStore",
    "ExecutionRegistry",
    "RetryPolicy",
    "PipelineExecutor",
    "make_context",
    "task",
]
