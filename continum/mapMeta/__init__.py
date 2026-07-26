"""mapMeta — scans ``sample_data/<Dataset>/``, loads every dataset into one
DuckDB (keeping the Xometry medallion ``gold_experiment_analysis`` gold view),
and emits per-dataset metadata that powers AskData + ContextGraph.

Folds the former ``contextmate/`` (synthetic generation, discovery, contracts,
bootstrap) and ``datastore/loader.py`` (medallion ELT), plus the static dataset
registry that used to live in ``askdata/metadata.py`` (now :mod:`.scanner`).
"""

from .bootstrap import bootstrap_from_connection
from .loader import (
    build_gold_layer,
    build_silver_layer,
    list_experiments,
    load_csvs,
    register_bronze,
    register_file_datasets,
    setup_database,
)
from .scanner import (
    METADATA,
    SEMANTIC_OVERLAY,
    get_active_dataset_name,
    get_display_name,
    get_metadata,
    list_datasets,
    scan_datasets,
    write_metadata,
)
from .synthetic_generator import EXPERIMENT_REGISTRY, ensure_sample_data, generate_all

__all__ = [
    # loader / warehouse
    "load_csvs",
    "register_bronze",
    "build_silver_layer",
    "build_gold_layer",
    "register_file_datasets",
    "list_experiments",
    "setup_database",
    # bootstrap
    "bootstrap_from_connection",
    # synthetic data
    "ensure_sample_data",
    "generate_all",
    "EXPERIMENT_REGISTRY",
    # metadata / scan
    "get_metadata",
    "get_active_dataset_name",
    "list_datasets",
    "get_display_name",
    "METADATA",
    "SEMANTIC_OVERLAY",
    "scan_datasets",
    "write_metadata",
]


def run_schema_discovery(*args, **kwargs):
    """Lazy proxy to the Discovery-phase schema profiler (kept out of import path
    to avoid pulling pandas/pdf at package import)."""
    from .discovery import run_schema_discovery as _f

    return _f(*args, **kwargs)


def run_data_validation(*args, **kwargs):
    from .discovery import run_data_validation as _f

    return _f(*args, **kwargs)


def run_dimension_setup(*args, **kwargs):
    from .discovery import run_dimension_setup as _f

    return _f(*args, **kwargs)
