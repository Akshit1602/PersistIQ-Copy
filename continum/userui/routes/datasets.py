import sqlite3
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/datasets", tags=["Loaded Datasets & Snippets"])

DB_PATH = "matchview_omnichannel.db"

@router.get("", response_model=List[Dict[str, Any]])
def get_dataset_snippets(limit: int = Query(5, ge=1, le=50)):
    """
    Returns loaded dataset table schemas, total row counts, column lists, and sample row snippets.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Get all non-internal tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row[0] for row in cursor.fetchall()]

        result = []
        for tbl in sorted(tables):
            # Fetch row count
            cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
            row_count = cursor.fetchone()[0]

            # Fetch columns
            cursor.execute(f"PRAGMA table_info({tbl})")
            columns = [col[1] for col in cursor.fetchall()]

            # Fetch sample rows
            cursor.execute(f"SELECT * FROM {tbl} LIMIT ?", (limit,))
            sample_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            domain = "ecomm" if tbl.startswith("ecomm_") else ("store" if tbl.startswith("store_") else "system")

            result.append({
                "table_name": tbl,
                "domain": domain,
                "row_count": row_count,
                "columns": columns,
                "sample_rows": sample_rows,
            })

        conn.close()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
