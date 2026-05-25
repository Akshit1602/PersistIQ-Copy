from __future__ import annotations
import logging
from typing import Dict, List, Optional
logger = logging.getLogger("continum.discovery.catalog")

def scan_catalog(db) -> List[Dict]:
    tables = []
    for query in [
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name",
        "SHOW TABLES",
    ]:
        try:
            df = db.execute(query).df()
            col = df.columns[0]
            for name in df[col].tolist():
                tables.append({"table_name": name, "row_estimate": None, "col_count": None})
            logger.info("Catalog: %d tables found", len(tables))
            return tables
        except Exception:
            continue
    return tables

def estimate_row_counts(db, tables: List[Dict]) -> List[Dict]:
    out = []
    for t in tables:
        name = t["table_name"]
        try:
            n = db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            out.append({**t, "row_estimate": int(n)})
        except Exception:
            out.append(t)
    return out

__all__ = ["scan_catalog", "estimate_row_counts"]
