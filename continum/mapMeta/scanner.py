from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect

from continum.config import settings, get_db_connection, STATIC_DOMAIN_TABLES, DYNAMIC_EXPERIMENT_TABLES
from continum.mapMeta.metadata_store import DATASET_METADATA
from continum.state import MetricDefinition, SchemaMetadata


class ScannerInput(BaseModel):
    database_url: Optional[str] = Field(
        None, description="Database connection URI. Defaults to settings.DATABASE_URL."
    )


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


class MetadataScanner:
    def __init__(self):
        self.cached_profiles: Dict[str, Any] = {}

    def profile_static_tables_once(self) -> Dict[str, Any]:
        """Profiles static/immutable domain tables upon application startup."""
        conn = get_db_connection()
        cursor = conn.cursor()
        for table in STATIC_DOMAIN_TABLES:
            if table not in self.cached_profiles:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    row_count = cursor.fetchone()[0]
                    self.cached_profiles[table] = {"row_count": row_count, "type": "static"}
                except Exception as e:
                    self.cached_profiles[table] = {"error": str(e), "type": "static"}
        conn.close()
        return self.cached_profiles

    def reprofile_dynamic_tables(self, domain_context: str = "ecomm") -> Dict[str, Any]:
        """Re-scans dynamic experiment tables following analysis or execution runs."""
        prefix = DATASET_METADATA.get(domain_context, DATASET_METADATA["ecomm"])["namespace_prefix"]
        conn = get_db_connection()
        cursor = conn.cursor()

        target_tables = [t for t in DYNAMIC_EXPERIMENT_TABLES if t.startswith(prefix)]
        for table in target_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                row_count = cursor.fetchone()[0]
                self.cached_profiles[table] = {"row_count": row_count, "type": "dynamic"}
            except Exception as e:
                self.cached_profiles[table] = {"error": str(e), "type": "dynamic"}

        conn.close()
        return self.cached_profiles