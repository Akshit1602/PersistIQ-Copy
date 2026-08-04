from langgraph.graph import END, START, StateGraph

from continum.state import AgentState, SchemaMetadata


def scan_database_schema_node(state: AgentState) -> dict:
    """Introspects DB tables and column definitions."""
    metadata = state.get("schema_metadata") or SchemaMetadata()
    metadata.tables = ["users", "orders", "exposures", "experiments"]
    metadata.schema_summary = "Target DB scanned. Identified exposure and purchase tables."
    return {"schema_metadata": metadata}


def catalog_experiments_node(state: AgentState) -> dict:
    """Indexes legacy and currently active experiments."""
    metadata = state.get("schema_metadata") or SchemaMetadata()
    metadata.cataloged_experiments = [
        {
            "experiment_id": "exp_checkout_redesign",
            "status": "RUNNING",
            "primary_metric": "conversion_rate",
        },
        {"experiment_id": "exp_cart_cross_sell_v1", "status": "COMPLETED", "primary_metric": "aov"},
    ]
    return {"schema_metadata": metadata}


builder = StateGraph(AgentState)
builder.add_node("scan_schema", scan_database_schema_node)
builder.add_node("catalog_experiments", catalog_experiments_node)

builder.add_edge(START, "scan_schema")
builder.add_edge("scan_schema", "catalog_experiments")
builder.add_edge("catalog_experiments", END)

ingestion_subgraph = builder.compile()
