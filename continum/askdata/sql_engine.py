from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from continum.config import settings


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
