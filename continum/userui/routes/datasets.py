import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

datasets_router = APIRouter(prefix="/api/datasets", tags=["Loaded Datasets"])

DB_PATH = Path(__file__).resolve().parents[2] / "matchview_omnichannel.db"
if not DB_PATH.exists():
    DB_PATH = Path("matchview_omnichannel.db")


def get_db_connection():
    if not DB_PATH.exists():
        raise HTTPException(status_code=500, detail="Database file matchview_omnichannel.db not found.")
    try:
        import duckdb
        return duckdb.connect(str(DB_PATH), read_only=True)
    except Exception:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn


@datasets_router.get("")
def get_loaded_datasets(table: Optional[str] = Query(None, description="Filter for a specific table")):
    """
    Returns summary metadata, column statistics, and sample rows for all loaded database tables.
    """
    try:
        conn = get_db_connection()
        is_sqlite = isinstance(conn, sqlite3.Connection)

        if is_sqlite:
            tables_res = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            all_tables = [t[0] for t in tables_res]
        else:
            tables_res = conn.execute("SHOW TABLES").fetchall()
            all_tables = [t[0] for t in tables_res]

        if table and table in all_tables:
            target_tables = [table]
        else:
            target_tables = all_tables

        datasets_summary = []

        for tbl in target_tables:
            count_res = conn.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()
            total_rows = count_res[0] if count_res else 0

            if is_sqlite:
                columns_info = conn.execute(f'PRAGMA table_info("{tbl}")').fetchall()
                # PRAGMA returns: cid, name, type, notnull, dflt_value, pk
                cols_meta = []
                col_names = []
                for col in columns_info:
                    col_name = col[1]
                    col_type = col[2]
                    col_names.append(col_name)

                    try:
                        stats = conn.execute(f'''
                            SELECT
                                COUNT(*) - COUNT("{col_name}") as null_count,
                                COUNT(DISTINCT "{col_name}") as unique_count
                            FROM "{tbl}"
                        ''').fetchone()
                        null_cnt = stats[0] if stats else 0
                        uniq_cnt = stats[1] if stats else 0
                    except Exception:
                        null_cnt = 0
                        uniq_cnt = 0

                    numeric_summary = {}
                    if any(t in str(col_type).upper() for t in ["INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "BIGINT"]):
                        try:
                            num_stats = conn.execute(f'''
                                SELECT
                                    MIN("{col_name}"),
                                    MAX("{col_name}"),
                                    AVG("{col_name}")
                                FROM "{tbl}"
                            ''').fetchone()
                            if num_stats and num_stats[0] is not None:
                                numeric_summary = {
                                    "min": round(float(num_stats[0]), 2) if isinstance(num_stats[0], (int, float)) else str(num_stats[0]),
                                    "max": round(float(num_stats[1]), 2) if isinstance(num_stats[1], (int, float)) else str(num_stats[1]),
                                    "avg": round(float(num_stats[2]), 2) if isinstance(num_stats[2], (int, float)) else str(num_stats[2]),
                                }
                        except Exception:
                            pass

                    cols_meta.append({
                        "name": col_name,
                        "type": str(col_type),
                        "null_count": null_cnt,
                        "unique_count": uniq_cnt,
                        **numeric_summary
                    })
            else:
                columns_info = conn.execute(f'DESCRIBE "{tbl}"').fetchall()
                cols_meta = []
                col_names = [c[0] for c in columns_info]
                for col in columns_info:
                    col_name = col[0]
                    col_type = col[1]

                    try:
                        stats = conn.execute(f'''
                            SELECT
                                COUNT(*) - COUNT("{col_name}") as null_count,
                                COUNT(DISTINCT "{col_name}") as unique_count
                            FROM "{tbl}"
                        ''').fetchone()
                        null_cnt = stats[0] if stats else 0
                        uniq_cnt = stats[1] if stats else 0
                    except Exception:
                        null_cnt = 0
                        uniq_cnt = 0

                    numeric_summary = {}
                    if any(t in str(col_type).upper() for t in ["INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "BIGINT"]):
                        try:
                            num_stats = conn.execute(f'''
                                SELECT
                                    MIN("{col_name}"),
                                    MAX("{col_name}"),
                                    AVG("{col_name}")
                                FROM "{tbl}"
                            ''').fetchone()
                            if num_stats and num_stats[0] is not None:
                                numeric_summary = {
                                    "min": round(float(num_stats[0]), 2) if isinstance(num_stats[0], (int, float)) else str(num_stats[0]),
                                    "max": round(float(num_stats[1]), 2) if isinstance(num_stats[1], (int, float)) else str(num_stats[1]),
                                    "avg": round(float(num_stats[2]), 2) if isinstance(num_stats[2], (int, float)) else str(num_stats[2]),
                                }
                        except Exception:
                            pass

                    cols_meta.append({
                        "name": col_name,
                        "type": str(col_type),
                        "null_count": null_cnt,
                        "unique_count": uniq_cnt,
                        **numeric_summary
                    })

            sample_res = conn.execute(f'SELECT * FROM "{tbl}" LIMIT 15').fetchall()

            sample_rows = []
            for row in sample_res:
                row_dict = {}
                for idx, val in enumerate(row):
                    row_dict[col_names[idx]] = str(val) if val is not None else None
                sample_rows.append(row_dict)

            datasets_summary.append({
                "table_name": tbl,
                "total_rows": total_rows,
                "column_count": len(col_names),
                "columns": cols_meta,
                "sample_data": sample_rows
            })

        conn.close()
        return {
            "status": "success",
            "tables_count": len(all_tables),
            "datasets": datasets_summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch dataset metadata: {str(e)}")
