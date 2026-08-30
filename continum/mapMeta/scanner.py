from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect

from continum.config import DYNAMIC_EXPERIMENT_TABLES, STATIC_DOMAIN_TABLES, settings
from continum.state import MetricDefinition, SchemaMetadata


class ScannerInput(BaseModel):
    database_url: Optional[str] = Field(
        None, description="Database connection URI. Defaults to settings.DATABASE_URL."
    )


_STATIC_CACHE: Optional[SchemaMetadata] = None


def profile_static_tables(database_url: Optional[str] = None) -> SchemaMetadata:
    """
    Profiles STATIC_DOMAIN_TABLES once at server startup (matching ecomm_* or store_*).
    """
    global _STATIC_CACHE
    if _STATIC_CACHE is not None:
        return _STATIC_CACHE

    db_url = database_url or settings.DATABASE_URL

    try:
        engine = create_engine(db_url)
        inspector = inspect(engine)

        all_tables = inspector.get_table_names()
        # Filter tables that match static domain entities
        static_tables = [
            t for t in all_tables
            if any(t.replace("ecomm_", "").replace("store_", "") in STATIC_DOMAIN_TABLES for _ in [1])
            and not any(d in t for d in DYNAMIC_EXPERIMENT_TABLES)
        ]

        schema_summary_parts = []
        metrics_catalog = {}

        for table in static_tables:
            columns = inspector.get_columns(table)
            col_names = [col["name"] for col in columns]
            schema_summary_parts.append(f"Table '{table}': [{', '.join(col_names)}]")

            for col in columns:
                col_type = str(col["type"]).upper()
                if any(t in col_type for t in ["INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"]):
                    metric_key = f"{table}.{col['name']}"
                    metrics_catalog[metric_key] = MetricDefinition(
                        name=col["name"],
                        table=table,
                        column=col["name"],
                        aggregation=(
                            "SUM"
                            if "amount" in col["name"].lower() or "price" in col["name"].lower()
                            else "AVG"
                        ),
                        description=f"Auto-discovered static metric from {table}.{col['name']}",
                    )

        summary_text = f"Scanned {len(static_tables)} static tables. " + " | ".join(schema_summary_parts)

        _STATIC_CACHE = SchemaMetadata(
            tables=static_tables,
            schema_summary=summary_text,
            metrics_catalog=metrics_catalog,
            cataloged_experiments=[],
        )
        return _STATIC_CACHE

    except Exception as e:
        return SchemaMetadata(
            tables=[],
            schema_summary=f"Static Schema Scanning Failed: {str(e)}",
            metrics_catalog={},
            cataloged_experiments=[],
        )


def reprofile_dynamic_tables(
    domain: str,
    database_url: Optional[str] = None,
    current_metadata: Optional[SchemaMetadata] = None,
) -> SchemaMetadata:
    """
    Scans DYNAMIC_EXPERIMENT_TABLES incrementally after module executions for a given domain ('ecomm' or 'store').
    """
    db_url = database_url or settings.DATABASE_URL
    base_meta = current_metadata or profile_static_tables(db_url)

    try:
        engine = create_engine(db_url)
        inspector = inspect(engine)

        all_tables = inspector.get_table_names()
        prefix = f"{domain}_"
        dynamic_tables = [
            t for t in all_tables
            if t.startswith(prefix) and t.replace(prefix, "") in DYNAMIC_EXPERIMENT_TABLES
        ]

        existing_tables = set(base_meta.tables)
        existing_metrics = dict(base_meta.metrics_catalog)
        schema_summary_parts = []

        for table in dynamic_tables:
            existing_tables.add(table)
            columns = inspector.get_columns(table)
            col_names = [col["name"] for col in columns]
            schema_summary_parts.append(f"Dynamic Table '{table}': [{', '.join(col_names)}]")

            for col in columns:
                col_type = str(col["type"]).upper()
                if any(t in col_type for t in ["INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"]):
                    metric_key = f"{table}.{col['name']}"
                    existing_metrics[metric_key] = MetricDefinition(
                        name=col["name"],
                        table=table,
                        column=col["name"],
                        aggregation="AVG",
                        description=f"Dynamic metric from {table}.{col['name']}",
                    )

        summary_text = (
            f"{base_meta.schema_summary} | Reprofiled dynamic {domain} tables: "
            + " | ".join(schema_summary_parts)
        )

        return SchemaMetadata(
            tables=sorted(list(existing_tables)),
            schema_summary=summary_text,
            metrics_catalog=existing_metrics,
            cataloged_experiments=base_meta.cataloged_experiments,
        )

    except Exception as e:
        return base_meta


def scan_database_schema(input_data: Optional[ScannerInput] = None) -> SchemaMetadata:
    """
    Introspects target database tables and columns using SQLAlchemy.
    """
    db_url = (
        input_data.database_url if input_data and input_data.database_url else settings.DATABASE_URL
    )

    try:
        engine = create_engine(db_url)
        inspector = inspect(engine)

        table_names = inspector.get_table_names()
        schema_summary_parts = []
        metrics_catalog = {}

        for table in table_names:
            columns = inspector.get_columns(table)
            col_names = [col["name"] for col in columns]
            schema_summary_parts.append(f"Table '{table}': [{', '.join(col_names)}]")

            # Auto-discover metric columns (numeric types)
            for col in columns:
                col_type = str(col["type"]).upper()
                if any(t in col_type for t in ["INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"]):
                    metric_key = f"{table}.{col['name']}"
                    metrics_catalog[metric_key] = MetricDefinition(
                        name=col["name"],
                        table=table,
                        column=col["name"],
                        aggregation=(
                            "SUM"
                            if "amount" in col["name"].lower() or "price" in col["name"].lower()
                            else "AVG"
                        ),
                        description=f"Auto-discovered metric from {table}.{col['name']}",
                    )

        summary_text = f"Scanned {len(table_names)} tables. " + " | ".join(schema_summary_parts)

        return SchemaMetadata(
            tables=table_names,
            schema_summary=summary_text,
            metrics_catalog=metrics_catalog,
            cataloged_experiments=[],
        )

    except Exception as e:
        return SchemaMetadata(
            tables=[],
            schema_summary=f"Schema Scanning Failed: {str(e)}",
            metrics_catalog={},
            cataloged_experiments=[],
        )
