"""AskData · VisualGenerator — a Plotly chart spec from the SQL result.

A single LangGraph node body (wired by :mod:`continum.orchestration`) that picks
one line/bar/pie chart when a chart genuinely helps, with a deterministic
fallback so a weak LLM response never silently drops an obviously chartable
result. Returns ``visualizations`` (a list of Plotly specs) rendered client-side.
"""

from __future__ import annotations

import json
import logging
import re
from io import StringIO
from typing import Optional

import pandas as pd

from continum import get_chat_llm

logger = logging.getLogger("continum.AskData.VisualGenerator")


def _llm(passed=None):
    return passed if passed is not None else get_chat_llm()


def _fallback_chart(df) -> Optional[dict]:
    """Build a sensible default Plotly config when the LLM declines but the data is
    clearly chartable (caller guarantees >=2 rows, >=2 cols, a numeric col)."""
    try:
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        non_numeric = [c for c in df.columns if c not in numeric_cols]
        if not numeric_cols:
            return None
        y = numeric_cols[0]
        time_cols = [
            c
            for c in df.columns
            if re.search(r"date|time|day|week|month|period", str(c), re.IGNORECASE)
        ]
        if time_cols:
            x, ctype = time_cols[0], "line"
        elif non_numeric:
            x, ctype = non_numeric[0], "bar"
        else:
            x, ctype = df.columns[0], "bar"
            y = numeric_cols[1] if len(numeric_cols) > 1 else numeric_cols[0]
        cfg = {"type": ctype, "x": str(x), "y": str(y), "title": f"{y} by {x}"}
        extra_cat = [c for c in non_numeric if c != x]
        if extra_cat:
            cfg["color"] = str(extra_cat[0])
        return cfg
    except Exception:
        logger.exception("fallback chart construction failed")
        return None


def visualization_node(state: dict, llm=None) -> dict:
    logger.info("Entering visualization_node")
    llm = _llm(llm)
    user_question = state["user_question"]
    df_json = state.get("dataframe_json")

    if not df_json:
        return {"current_step_index": state.get("current_step_index", 0) + 1}

    df = pd.read_json(StringIO(df_json))
    # Deterministic guard: a chart only makes sense for a comparable set of values.
    n_rows, n_cols = df.shape
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if df.empty or n_rows < 2 or n_cols < 2 or not numeric_cols:
        logger.info(
            "visualization_node: skipping chart (rows=%s cols=%s numeric=%s)",
            n_rows,
            n_cols,
            len(numeric_cols),
        )
        return {"visualizations": [], "current_step_index": state.get("current_step_index", 0) + 1}

    data_sample = df.head(5).to_dict(orient="records")
    column_info = df.dtypes.apply(lambda x: str(x)).to_dict()

    viz_prompt = f"""
    You are a data visualization expert. Suggest a Plotly Express chart (line, bar, pie)
    ONLY when a chart genuinely helps the user read the answer.

    User Question: {user_question}
    Data Sample: {data_sample}
    Columns: {column_info}

    Return an EMPTY list [] (no chart) when a visual would not help, e.g.:
    - the answer is a single value / single row, or a yes-no / textual answer
    - there is no meaningful category-vs-metric or time-vs-metric relationship to show
    - the data is just an ID list or a raw record dump with no comparison
    - a table already conveys the answer more clearly than a chart would
    Prefer NO chart over a weak or misleading one.

    Mapping Rules:
    - For a trend over time -> use 'line' (x = the date/time column, y = the numeric metric).
    - For comparing several groups/series across the SAME x (e.g. revenue per product_family
      over date, or Treatment vs Control over time) -> use 'line' (or 'bar') AND set 'color' to
      the categorical column that distinguishes the series. This renders one line per series.
    - For comparisons between a few categories -> use 'bar' chart.
    - For distributions or percentages of a total -> use 'pie' chart.

    Series / color rules:
    - 'color' MUST be an exact column name present in the data that splits rows into series
      (e.g. 'product_family', 'group_name', 'cohort', 'city'). Omit 'color' for a single series.
    - 'x', 'y' and 'color' must be exact column names from the Columns list above.

    Strict Rules:
    - Limit to ONLY ONE best fitting visual.
    - Return ONLY a JSON list containing a single object (or an empty list if no visual is suitable).

    Output:
    Return ONLY the JSON list of objects with: 'type', 'x', 'y', 'values', 'names', 'color', 'title'.
    """

    response = llm.invoke(
        [
            ("system", "Return ONLY a JSON list of Plotly chart configurations."),
            ("human", viz_prompt),
        ]
    )

    try:
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        configs = json.loads(content)
        if not isinstance(configs, list):
            configs = [configs] if isinstance(configs, dict) else []
    except Exception:
        logger.warning("visualization_node: could not parse chart config; using fallback")
        configs = []

    # Deterministic fallback: data passed the chartable guard, so if the LLM declined
    # (or returned junk) build a sensible default rather than showing nothing.
    if not configs:
        fb = _fallback_chart(df)
        if fb is not None:
            logger.info("visualization_node: using deterministic fallback %s", fb)
            configs = [fb]

    return {
        "visualizations": configs,
        "current_step_index": state.get("current_step_index", 0) + 1,
    }


__all__ = ["visualization_node", "_fallback_chart"]
