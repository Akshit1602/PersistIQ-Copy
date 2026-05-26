import os

# Central configuration for runtime data
RUNTIME_DATA_DIR = "runtime_data"

def ensure_runtime_data_dir():
    """Ensure the runtime data directory exists."""
    os.makedirs(RUNTIME_DATA_DIR, exist_ok=True)
