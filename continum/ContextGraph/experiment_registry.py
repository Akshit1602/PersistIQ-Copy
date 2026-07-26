"""
User-created experiment registry (JSON-backed).

The live experiment warehouse (``gold_experiment_analysis``) is an in-memory
DuckDB table rebuilt from the sample CSVs on every boot, so it only ever holds
the shipped Xometry A/B tests. This module adds a small, *persistent* registry
for experiments the user creates through the UI / Copilot — one metadata record
per experiment (no result rows required) — so a new experiment shows up in the
dropdowns immediately and survives a restart.

Records are keyed by ``experiment_name`` and carry the owning ``dataset`` so the
experiment dropdown can be filtered by the selected dataset. Analysis modules run
against a registry experiment once its data exists in the warehouse.

Storage: ``runtime_data/experiment_registry.json`` — a flat list of records.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from continum.paths import RUNTIME_DATA_DIR, ensure_runtime_data_dir

logger = logging.getLogger("continum.ContextGraph.experiment_registry")

ensure_runtime_data_dir()
REGISTRY_FILE = os.path.join(RUNTIME_DATA_DIR, "experiment_registry.json")

# Fields persisted per experiment. `variants` is a list of arm names.
_FIELDS = (
    "experiment_name",
    "dataset",
    "hypothesis",
    "variants",
    "primary_metric",
    "start_date",
    "end_date",
    "created_at",
)


def load_registry(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all registered experiment records (empty list when none / unreadable)."""
    path = path or REGISTRY_FILE
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict) and r.get("experiment_name")]
        logger.warning("Registry %s is not a list — ignoring", path)
        return []
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Could not read experiment registry %s: %s", path, e)
        return []


def list_registry(
    dataset: Optional[str] = None, path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Registered experiments, optionally filtered to a single ``dataset``.

    A blank/None ``dataset`` returns everything (the "no dataset selected → show
    all" case)."""
    records = load_registry(path)
    if not dataset:
        return records
    return [r for r in records if (r.get("dataset") or "") == dataset]


def experiment_exists(name: str, path: Optional[str] = None) -> bool:
    name = (name or "").strip()
    return any((r.get("experiment_name") or "") == name for r in load_registry(path))


def _save(records: List[Dict[str, Any]], path: str) -> None:
    ensure_runtime_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, default=str)


def add_experiment(
    experiment_name: str,
    dataset: str,
    hypothesis: str = "",
    variants: Optional[List[str]] = None,
    primary_metric: str = "",
    start_date: str = "",
    end_date: str = "",
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """Append a new experiment metadata record and persist it.

    Raises ``ValueError`` on an empty or duplicate name so the API layer can
    surface a 400. Names are compared against the registry only — the caller is
    responsible for rejecting collisions with warehouse experiment names.
    """
    path = path or REGISTRY_FILE
    name = (experiment_name or "").strip()
    if not name:
        raise ValueError("experiment_name is required")
    if experiment_exists(name, path):
        raise ValueError(f"experiment '{name}' already exists")

    record = {
        "experiment_name": name,
        "dataset": (dataset or "").strip(),
        "hypothesis": (hypothesis or "").strip(),
        "variants": [v.strip() for v in (variants or []) if str(v).strip()],
        "primary_metric": (primary_metric or "").strip(),
        "start_date": (start_date or "").strip(),
        "end_date": (end_date or "").strip(),
        "created_at": datetime.utcnow().isoformat(),
    }
    records = load_registry(path)
    records.append(record)
    _save(records, path)
    logger.info("Registered experiment '%s' under dataset '%s'", name, record["dataset"])
    return record


__all__ = [
    "REGISTRY_FILE",
    "load_registry",
    "list_registry",
    "experiment_exists",
    "add_experiment",
]
