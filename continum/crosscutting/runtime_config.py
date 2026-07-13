import os

# Central configuration for runtime data
RUNTIME_DATA_DIR = "runtime_data"

# Single canonical folder where module-generated output files (PDFs, CSVs, charts,
# captured result text) are collected so they're browsable + downloadable from the
# UI's Output tab. Overridable via CONTINUM_OUTPUT_DIR.
OUTPUTS_DIR = os.environ.get("CONTINUM_OUTPUT_DIR") or os.path.join(RUNTIME_DATA_DIR, "outputs")


def ensure_runtime_data_dir():
    """Ensure the runtime data directory exists."""
    os.makedirs(RUNTIME_DATA_DIR, exist_ok=True)


def ensure_outputs_dir() -> str:
    """Ensure the outputs directory exists and return its path."""
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    return OUTPUTS_DIR
