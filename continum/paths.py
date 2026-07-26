"""Where Continum's runtime state and generated output files live.

Single source of truth for every writer in the project (ContextGraph's stores,
ExpSuite's PDF-producing modules, mapMeta's schema reports, the userui Output
tab) — nothing should hardcode a bare relative filename like ``"report.pdf"``;
that lands wherever the process's current working directory happens to be
(e.g. the repo root) instead of inside ``runtime_data/``.
"""

import os
import uuid

# Central directory for all runtime/session state (gitignored).
RUNTIME_DATA_DIR = "runtime_data"

# Single canonical folder where module-generated output files (PDFs, CSVs,
# charts, captured result text) are collected so they're browsable +
# downloadable from the UI's Output tab. Overridable via CONTINUM_OUTPUT_DIR.
OUTPUTS_DIR = os.environ.get("CONTINUM_OUTPUT_DIR") or os.path.join(RUNTIME_DATA_DIR, "outputs")


def ensure_runtime_data_dir():
    """Ensure the runtime data directory exists."""
    os.makedirs(RUNTIME_DATA_DIR, exist_ok=True)


def ensure_outputs_dir() -> str:
    """Ensure the outputs directory exists and return its path."""
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    return OUTPUTS_DIR


def new_run_dir(module_key: str, run_id: str = "") -> str:
    """Create and return a fresh, per-run output directory for one module run:

        runtime_data/outputs/<module_key>/<run_id>/

    Always an absolute-safe path under OUTPUTS_DIR — never a bare relative
    filename — so a module's generated files can never land in the process's
    current working directory. Pass ``run_id`` to share a folder with a
    caller-generated id (e.g. the execution console's run_id); otherwise a
    fresh one is minted.
    """
    run_id = run_id or uuid.uuid4().hex[:8]
    d = os.path.join(ensure_outputs_dir(), module_key, run_id)
    os.makedirs(d, exist_ok=True)
    return d


__all__ = [
    "RUNTIME_DATA_DIR",
    "OUTPUTS_DIR",
    "ensure_runtime_data_dir",
    "ensure_outputs_dir",
    "new_run_dir",
]
