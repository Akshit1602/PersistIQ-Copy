from langgraph.graph import END, START, StateGraph

from continum.AskData import SQLExecutionInput, execute_sql_query
from continum.mapMeta import (
    IndexExperimentsInput,
    ScannerInput,
    catalog_experiments,
    scan_database_schema,
)
from continum.state import IngestionState, SchemaMetadata


def scan_database_schema_node(state: IngestionState) -> dict:
    """Introspects DB tables and column definitions."""
    metadata = scan_database_schema(ScannerInput())
    return {
        "schema_metadata": metadata,
        "raw_tables_discovered": metadata.tables,
    }


def catalog_experiments_node(state: IngestionState) -> dict:
    """Indexes legacy and currently active experiments."""
    metadata = state.get("schema_metadata") or SchemaMetadata()

    # `catalog_experiments` extends metadata with rows it is handed; it does not
    # discover them. Source them from whichever scanned table looks like the
    # experiment log. The name comes from the database's own catalog via
    # SQLAlchemy inspection, not from user input.
    table = next((t for t in metadata.tables if "experiment" in t.lower()), None)
    if table is None:
        return {
            "errors": [
                "No experiments table found among scanned tables: " f"{metadata.tables or 'none'}"
            ]
        }

    query = execute_sql_query(SQLExecutionInput(query=f"SELECT * FROM {table} LIMIT 50"))
    if not query.is_safe or query.row_count == 0:
        return {"errors": [query.summary]}

    updated = catalog_experiments(
        IndexExperimentsInput(current_metadata=metadata, experiments=query.rows)
    )
    return {"schema_metadata": updated}


builder = StateGraph(IngestionState)
builder.add_node("scan_schema", scan_database_schema_node)
builder.add_node("catalog_experiments", catalog_experiments_node)

builder.add_edge(START, "scan_schema")
builder.add_edge("scan_schema", "catalog_experiments")
builder.add_edge("catalog_experiments", END)

ingestion_subgraph = builder.compile()
