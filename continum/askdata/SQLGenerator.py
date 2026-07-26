"""AskData · SQLGenerator — NL → SQL over the active dataset's DuckDB schema.

Two LangGraph node bodies (wired into the graph by :mod:`continum.orchestration`):

* :func:`refine_node` — breaks the raw user question down into SQL-friendly terms
  grounded in the DuckDB schema of the relevant dataset (mandatory before SQL).
* :func:`sql_node` — generates a DuckDB ``SELECT`` and executes it on the live
  connection, with a self-correction retry loop on execution errors.
* :func:`clarification_node` — when SQL keeps failing, suggests answerable questions.

Schema/description context comes from :mod:`continum.mapMeta`; the chat model comes
from :func:`continum.get_chat_llm` (LangChain). Runs directly on DuckDB (no SQLite
snapshot) so ``SQLGenerator`` reasons over the real dataset schema.
"""

from __future__ import annotations

import json
import logging
import re

from continum import get_chat_llm
from continum.mapMeta import get_metadata

logger = logging.getLogger("continum.AskData.SQLGenerator")


def _llm(passed=None):
    return passed if passed is not None else get_chat_llm()


def _clean_sql(raw: str) -> str:
    """Strip markdown code fences and a leading 'sql' language tag from LLM output."""
    text = (raw or "").strip()
    fence = re.match(r"^```(?:sql)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    else:
        text = text.replace("```", "").strip()
        text = re.sub(r"^sql\s+", "", text, flags=re.IGNORECASE)
    return text.strip()


def refine_node(state: dict, llm=None) -> dict:
    """Map the user request onto the schema and resolve references/follow-ups."""
    logger.info("Entering refine_node")
    llm = _llm(llm)
    user_question = state["user_question"]
    history = state.get("history", "")
    structured_context = state.get("structured_context", "{}")
    metadata = get_metadata()
    domain_context = metadata["domain_context"]
    table_info = metadata["table_info_combined"]

    prompt = f"""
    You are a Query Refinement Expert for an {domain_context} data assistant.
    Your primary goal is to map the user's natural language request to the provided Database Schema, using the conversation history ONLY to resolve ambiguities or references.

    ### DATABASE SCHEMA (Primary Source of Truth):
    {table_info}

    ### CONTEXT (Secondary):
    History Summary: {history}
    Structured State: {structured_context}

    ### USER QUESTION:
    {user_question}

    ### INSTRUCTIONS:
    1. ALWAYS prioritize the Database Schema. If the user mentions a term, find its closest equivalent in the schema columns or tables.
    2. Resolve any references (e.g., "it", "them", "that city", "previous group") by looking at the History and Structured State.
    2. If it's a follow-up, merge the previous constraints with the new question.
       Example:
       Turn 1: "Show sales for Bangalore"
       Turn 2: "What about Chennai?"
       Refined: "Show sales for Chennai"
    3. If the user uses pronouns (e.g., "their revenue"), resolve them to the specific entities previously mentioned.
    4. If the question is already self-contained, return it as is.
    5. Return ONLY a JSON object with a single key 'refined_question'.
    """

    response = llm.invoke(prompt)
    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        refined_question = json.loads(content).get("refined_question", user_question)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to parse refined question: %s", e)
        refined_question = user_question

    logger.info("Refined question: %s", refined_question)
    return {
        "refined_question": refined_question,
        "current_step_index": state.get("current_step_index", 0) + 1,
    }


def sql_node(state: dict, db=None, llm=None) -> dict:
    """Generate a DuckDB SELECT for the refined question and execute it on ``db``."""
    logger.info("Entering sql_node")
    llm = _llm(llm)
    user_question = state.get("refined_question") or state["user_question"]
    history = state.get("history", "")
    structured_context = state.get("structured_context", "{}")
    retry_count = state.get("retry_count", 0)
    error = state.get("error")

    metadata = get_metadata()
    domain_context = metadata["domain_context"]
    column_descriptions = metadata["column_descriptions"]
    relationships = metadata["relationships"]
    table_info_combined = metadata["table_info_combined"]
    table_descriptions = metadata.get("table_descriptions", {})

    if error:
        system_msg = (
            f"You are a SQL Self-Correction Expert for {domain_context}. The previous SQL failed "
            f"with error: {error}. Focus on fixing column names and join conditions based on the "
            "Database Schema. Target dialect: DuckDB."
        )
        user_prompt = f"""
        ### DATABASE SCHEMA (Source of Truth):
        Tables and Columns: {json.dumps(column_descriptions, indent=2)}
        Table Info (DDL-like): {table_info_combined}
        Table Descriptions: {json.dumps(table_descriptions, indent=2)}

        ### ERROR DIAGNOSTIC:
        The previous query failed.
        Error: {error}

        ### TASK:
        1. Review the Schema above. Ensure every column used exists in the 'Tables and Columns' JSON.
        2. Check for common DuckDB errors (types, quoting, aggregates).
        3. Provide a CORRECTED SELECT query.

        Return ONLY the corrected DuckDB SELECT query.
        """
    else:
        system_msg = (
            f"You are an {domain_context} DuckDB SQL expert. Your primary task is to translate "
            "natural language into SQL based on the official Database Schema."
        )
        user_prompt = f"""
        ### DATABASE SCHEMA (Primary Source of Truth):
        Tables and Columns:
        {json.dumps(column_descriptions, indent=2)}
        Relationships: {json.dumps(relationships, indent=2)}
        Table Info (DDL-like): {table_info_combined}

        ### CONTEXT (Secondary):
        History: {history}
        Structured State: {structured_context}

        ### CURRENT REQUEST:
        User Question: {user_question}

        ### INSTRUCTIONS:
        1. ALWAYS prioritize the Database Schema over the conversation history. If there is a conflict, the Schema wins.
        2. Use the 'Structured State' and 'History' ONLY to resolve references or to understand the user's iterative refinement of a query.
        - If the current question is a follow-up (e.g., "What about Bangalore?"), carry forward the previous metrics and constraints unless contradicted.
        - Return ONLY a valid DuckDB SELECT query.
        - No markdown, no comments.
        - LIMIT results to 50 unless specified.
        - Round numerical values to 2 decimal places.
        """

    response = llm.invoke([("system", system_msg), ("human", user_prompt)])
    sql_query = _clean_sql(response.content)
    logger.info("Executing SQL: %s", sql_query)

    try:
        df = db.execute(sql_query).df()  # DuckDB → DataFrame
        logger.info("SQL execution successful, returned %d rows.", len(df))
        return {
            "sql_query": sql_query,
            "dataframe_json": df.to_json(),
            "error": None,
            "retry_count": 0,
            "current_step_index": state.get("current_step_index", 0) + 1,
        }
    except Exception as e:  # noqa: BLE001
        logger.error("SQL execution failed: %s", e)
        return {
            "sql_query": sql_query,
            "error": str(e),
            "retry_count": retry_count + 1,
        }


def clarification_node(state: dict, llm=None) -> dict:
    """After repeated SQL failures, suggest three answerable questions."""
    logger.info("Entering clarification_node")
    llm = _llm(llm)
    metadata = get_metadata()
    table_info = metadata["table_info_combined"]

    prompt = f"""
    The SQL assistant failed to generate a valid query for the user.
    Based on the available tables and columns, suggest 3 sample questions the user could ask instead.

    Database Schema:
    {table_info}

    Return ONLY the 3 questions as a bulleted list.
    """
    suggestions = llm.invoke(prompt).content.strip()
    message = (
        "I'm sorry, I'm having trouble generating a valid query for your request after several attempts. "
        "Here are some alternative questions you might find useful based on the data I have:\n\n"
        f"{suggestions}"
    )
    return {
        "sql_query": None,
        "insight": message,
        "current_step_index": len(state.get("plan", [])),
    }


__all__ = ["refine_node", "sql_node", "clarification_node", "_clean_sql"]
