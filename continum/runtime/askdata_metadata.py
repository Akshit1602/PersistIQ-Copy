import duckdb
import json
import os

def get_metadata(db=None):
    """
    Dynamically discover metadata from the DuckDB instance.
    """
    if db is None:
        # Fallback to a new connection if none provided, though usually we pass the app's db
        db = duckdb.connect(":memory:")

    tables = {}
    try:
        # Get list of tables/views
        res = db.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()
        table_names = [r[0] for r in res]

        for table_name in table_names:
            # Get columns
            cols_res = db.execute(f"PRAGMA table_info('{table_name}')").fetchall()
            # PRAGMA table_info returns (cid, name, type, notnull, dflt_value, pk)
            columns = {r[1]: f"Type: {r[2]}" for r in cols_res}
            tables[table_name] = columns
    except Exception as e:
        print(f"Error discovering metadata: {e}")

    # Map to AskData style metadata
    metadata = {
        "domain_context": "expert product analytics assistant for PersistIQ, specialized in experimentation and causal inference",
        "table_descriptions": {
            "silver_inquiries": "Contains cleaned inquiry data with conversion status and order values.",
            "gold_experiment_analysis": "Contains aggregated experiment results, variant assignments, and performance metrics."
        },
        "column_descriptions": tables,
        "relationships": {},
        "table_info_combined": ""
    }

    # Generate table_info_combined string
    info_parts = []
    for table_name, columns in tables.items():
        col_str = ", ".join(columns.keys())
        info_parts.append(f"{table_name}({col_str})")
    metadata["table_info_combined"] = "\n".join(info_parts) + "\n"

    return metadata
