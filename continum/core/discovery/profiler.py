from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
logger = logging.getLogger("continum.discovery.profiler")

def profile_table(db, table_name: str, sample_n: int = 5000) -> Dict:
    try:
        df = db.execute(f'SELECT * FROM "{table_name}" LIMIT {sample_n}').df()
    except Exception as e:
        return {"error": str(e), "table_name": table_name}
    cols = {}
    for col in df.columns:
        s = df[col]
        null_rate = float(s.isna().mean())
        n_unique  = int(s.nunique())
        dtype_str = str(s.dtype)
        try:
            sample_vals = s.dropna().head(3).tolist()
        except Exception:
            sample_vals = []
        cols[col] = {
            "dtype":      dtype_str,
            "null_rate":  round(null_rate, 3),
            "n_unique":   n_unique,
            "n_sampled":  len(df),
            "sample":     sample_vals,
            "is_likely_id":  n_unique / max(len(df), 1) > 0.95,
            "is_likely_cat": n_unique < 30 and null_rate < 0.5,
        }
    logger.info("Profiled %s: %d cols", table_name, len(cols))
    return {"table_name": table_name, "n_sampled": len(df), "columns": cols}

__all__ = ["profile_table"]
