from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from continum.config import settings
from continum.mapMeta.metadata_store import DATASET_METADATA


class SQLExecutionInput(BaseModel):
    query: str = Field(..., description="Natural language question or raw SQL statement")
    schema_context: Optional[str] = Field(
        None, description="Schema definition string for Text-to-SQL generation"
    )
    domain_context: Optional[str] = Field(
        "ecomm", description="Domain namespace context ('ecomm' or 'store')"
    )


def generate_sql_query(question: str, domain_context: str = "ecomm") -> str:
    """
    Generates domain-aware SQL query based on natural language question and DATASET_METADATA schema rules.
    """
    meta = DATASET_METADATA.get(domain_context, DATASET_METADATA["ecomm"])
    prefix = meta["table_prefix"]
    tables = meta["tables"]
    join_keys = meta["join_keys"]

    system_prompt = (
        f"You are a SQL query generator for the {meta['description']} domain context ('{domain_context}').\n"
        f"ALWAYS use the '{prefix}' table prefix for all referenced tables.\n\n"
        "TABLE SCHEMA DEFINITIONS:\n"
        + "\n".join([f"- {tbl}: {desc}" for tbl, desc in tables.items()])
        + "\n\nEXPLICIT JOIN KEYS:\n"
        + "\n".join([f"- {src} JOIN {tgt}" for src, tgt in join_keys.items()])
        + f"\n\nRULES:\n"
        f"1. Generate only SQLite-compatible SELECT queries using '{prefix}' prefixed tables.\n"
        f"2. Joins must follow explicit join keys matching the domain schema.\n"
        f"3. Any write operations are strictly constrained to '{prefix}experiment_*' dynamic tables.\n"
    )

    try:
        llm = settings.get_llm()
        messages = [
            ("system", system_prompt),
            ("human", f"Generate SQL for question: {question}"),
        ]
        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)
        sql = str(content).strip()
        if sql.startswith("```sql"):
            sql = sql.replace("```sql", "").replace("```", "").strip()
        return sql
    except Exception:
        # Rule-based fallback query generator
        lower_q = question.lower()
        if domain_context == "ecomm":
            if "conversion" in lower_q or "cad" in lower_q or "pricing" in lower_q:
                return (
                    "SELECT e.experiment_id, e.name, er.metric_id, er.raw_mean, "
                    "er.cuped_mean, er.relative_lift_pct, er.p_value "
                    "FROM ecomm_experiments e "
                    "JOIN ecomm_experiment_results er ON e.experiment_id = er.experiment_id "
                    "WHERE e.name LIKE '%Pricing%' OR e.name LIKE '%CAD%';"
                )
            return (
                "SELECT e.experiment_id, e.name, er.metric_id, er.relative_lift_pct "
                "FROM ecomm_experiments e "
                "JOIN ecomm_experiment_results er ON e.experiment_id = er.experiment_id;"
            )
        else:
            if "dwell" in lower_q or "endcap" in lower_q or "kiosk" in lower_q or "store" in lower_q:
                return (
                    "SELECT s.store_id, s.store_name, f.zone, AVG(f.dwell_time_seconds) as avg_dwell_seconds "
                    "FROM store_stores s "
                    "JOIN store_foot_traffic_events f ON s.store_id = f.store_id "
                    "WHERE f.zone LIKE '%Endcap%' OR f.zone LIKE '%Kiosk%' OR f.zone LIKE '%Queue%' "
                    "GROUP BY s.store_id, s.store_name, f.zone;"
                )
            return (
                "SELECT s.store_id, s.store_name, er.metric_name, er.relative_lift_pct "
                "FROM store_stores s "
                "JOIN store_experiment_assignments sa ON s.store_id = sa.store_id "
                "JOIN store_experiment_results er ON sa.experiment_id = er.experiment_id;"
            )


class SQLExecutionInput(BaseModel):
    query: str = Field(..., description="Natural language question or raw SQL statement")
    schema_context: Optional[str] = Field(
        None, description="Schema definition string for Text-to-SQL generation"
    )


class SQLExecutionResult(BaseModel):
    sql_statement: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int
    is_safe: bool
    summary: str


def validate_sql_safety(sql: str) -> bool:
    """
    Enforces read-only database query execution to prevent destructive SQL injections.
    """
    clean_sql = sql.strip().upper()
    forbidden_keywords = ["DROP", "DELETE", "TRUNCATE", "UPDATE", "INSERT", "ALTER", "CREATE"]

    if not clean_sql.startswith("SELECT") and not clean_sql.startswith("WITH"):
        return False

    for kw in forbidden_keywords:
        if f" {kw} " in clean_sql or clean_sql.startswith(f"{kw} "):
            return False

    return True


def execute_sql_query(input_data: SQLExecutionInput) -> SQLExecutionResult:
    """
    Validates and executes a SQL query against the configured database URL.
    """
    sql_query = input_data.query.strip()

    # Clean codeblock markdown markers if passed by LLM
    if sql_query.startswith("```sql"):
        sql_query = sql_query.replace("```sql", "").replace("```", "").strip()

    is_safe = validate_sql_safety(sql_query)
    if not is_safe:
        return SQLExecutionResult(
            sql_statement=sql_query,
            columns=[],
            rows=[],
            row_count=0,
            is_safe=False,
            summary="SECURITY ALERT: Query rejected. Only read-only SELECT statements are permitted.",
        )

    try:
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            result_proxy = conn.execute(text(sql_query))
            columns = list(result_proxy.keys())
            fetched_rows = [dict(zip(columns, row)) for row in result_proxy.fetchall()]

        return SQLExecutionResult(
            sql_statement=sql_query,
            columns=columns,
            rows=fetched_rows,
            row_count=len(fetched_rows),
            is_safe=True,
            summary=f"SQL Query executed successfully. Returned {len(fetched_rows)} rows.",
        )

    except Exception as e:
        return SQLExecutionResult(
            sql_statement=sql_query,
            columns=[],
            rows=[],
            row_count=0,
            is_safe=True,
            summary=f"SQL Execution Error: {str(e)}",
        )
