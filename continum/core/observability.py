from __future__ import annotations

import hashlib
import json
import logging
import logging.config
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURED LOGGING
# ─────────────────────────────────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts":       datetime.now(timezone.utc).isoformat(),
            "level":    record.levelname,
            "logger":   record.name,
            "message":  record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Copy any extra fields injected via logger.info(..., extra={...})
        for key in ("experiment_id", "run_id", "task_name", "analyst",
                    "metric", "p_value", "delta_pp"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, default=str)


def configure_logging(
    level: str = "INFO",
    mode:  str = "human",   # "human" | "json"
    log_file: Optional[str] = None,
) -> None:
    handlers: Dict[str, Any] = {}

    if mode == "json":
        handlers["console"] = {
            "class":     "logging.StreamHandler",
            "formatter": "json",
            "stream":    "ext://sys.stderr",
        }
    else:
        handlers["console"] = {
            "class":     "logging.StreamHandler",
            "formatter": "human",
            "stream":    "ext://sys.stderr",
        }

    if log_file:
        handlers["file"] = {
            "class":       "logging.FileHandler",
            "formatter":   "json",
            "filename":    log_file,
            "encoding":    "utf-8",
        }

    config = {
        "version":              1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": _JsonFormatter,
            },
            "human": {
                "format":   "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
                "datefmt":  "%H:%M:%S",
            },
        },
        "handlers": handlers,
        "loggers": {
            "continum": {
                "level":    level,
                "handlers": list(handlers.keys()),
                "propagate": False,
            },
        },
        "root": {
            "level":    "WARNING",
            "handlers": ["console"],
        },
    }
    logging.config.dictConfig(config)


def get_logger(name: str, **context) -> logging.Logger:
    logger = logging.getLogger(f"continum.{name}")
    if context:
        logger = logging.LoggerAdapter(logger, context)
    return logger


# ─────────────────────────────────────────────────────────────────────────────
# REPRODUCIBILITY GUARD
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReproducibilityGuard:
    source_name:    str
    n_rows:         int
    n_cols:         int
    columns:        list
    row_hash:       str       # SHA-256 of sorted row fingerprints
    schema_hash:    str       # SHA-256 of column names + dtypes
    created_at:     str
    continum_version: str = "0.3.0"

    @classmethod
    def from_dataframe(cls, df, source_name: str = "input") -> "ReproducibilityGuard":
        import pandas as pd
        import numpy as np

        # Row-level hash via pandas hash_pandas_object
        try:
            row_fingerprints = pd.util.hash_pandas_object(df, index=True)
            row_hash = hashlib.sha256(row_fingerprints.values.tobytes()).hexdigest()
        except Exception:
            row_hash = hashlib.sha256(str(df.shape).encode()).hexdigest()

        col_str   = json.dumps({c: str(t) for c, t in df.dtypes.items()}, sort_keys=True)
        schema_hash = hashlib.sha256(col_str.encode()).hexdigest()

        return cls(
            source_name=source_name,
            n_rows=len(df), n_cols=len(df.columns),
            columns=df.columns.tolist(),
            row_hash=row_hash[:16],
            schema_hash=schema_hash[:16],
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def verify(self, df, raise_on_mismatch: bool = True) -> bool:
        import pandas as pd
        current = self.from_dataframe(df, self.source_name)
        mismatches = []
        if current.n_rows != self.n_rows:
            mismatches.append(f"row count: {self.n_rows} → {current.n_rows}")
        if current.schema_hash != self.schema_hash:
            mismatches.append(f"schema changed (hash {self.schema_hash} → {current.schema_hash})")
        if current.row_hash != self.row_hash:
            mismatches.append(f"row data changed (hash {self.row_hash} → {current.row_hash})")

        if mismatches:
            msg = f"Reproducibility check FAILED for '{self.source_name}': " + "; ".join(mismatches)
            if raise_on_mismatch:
                raise ValueError(msg)
            logging.getLogger("continum.observability").warning(msg)
            return False
        return True

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(vars(self), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "ReproducibilityGuard":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return cls(**d)


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTION SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ExecutionSnapshot:
    snapshot_id:      str
    experiment_id:    str
    task_name:        str
    input_hash:       str
    output_hash:      str
    elapsed_ms:       int
    created_at:       str
    python_version:   str  = field(default_factory=lambda: sys.version.split()[0])
    os_name:          str  = field(default_factory=lambda: os.name)
    continum_version: str  = "0.3.0"

    def to_dict(self) -> Dict:
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def create(cls, experiment_id: str, task_name: str,
               input_obj: Any, output_obj: Any, elapsed_ms: int) -> "ExecutionSnapshot":
        def _h(obj):
            try:
                s = json.dumps(obj, sort_keys=True, default=str)
                return hashlib.sha256(s.encode()).hexdigest()[:12]
            except Exception:
                return hashlib.sha256(str(obj).encode()).hexdigest()[:12]

        return cls(
            snapshot_id=hashlib.sha256(
                f"{experiment_id}{task_name}{datetime.now().isoformat()}".encode()
            ).hexdigest()[:12],
            experiment_id=experiment_id,
            task_name=task_name,
            input_hash=_h(input_obj),
            output_hash=_h(output_obj),
            elapsed_ms=elapsed_ms,
            created_at=datetime.now(timezone.utc).isoformat(),
        )


__all__ = [
    "configure_logging",
    "get_logger",
    "ReproducibilityGuard",
    "ExecutionSnapshot",
]
