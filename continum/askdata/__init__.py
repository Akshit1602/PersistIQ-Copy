"""AskData — the AI-powered NL→SQL / Visualization / Insight layer.

Three generators, each exposing LangGraph node bodies that the
:mod:`continum.orchestration` graph wires together:

* :mod:`.SQLGenerator`   — refine/breakdown + NL→SQL on the dataset's DuckDB schema
* :mod:`.VisualGenerator`— a Plotly chart spec from the SQL result
* :mod:`.InsightGenerator` — short insights from the data or ContextGraph context

The graph topology + engine live in :mod:`continum.orchestration`, not here.
"""

from .InsightGenerator import (
    about,
    describe_result,
    get_readme_context,
    grounded_insight,
    insight_node,
    run_ask,
)
from .SQLGenerator import clarification_node, refine_node, sql_node
from .VisualGenerator import visualization_node

__all__ = [
    "refine_node",
    "sql_node",
    "clarification_node",
    "visualization_node",
    "insight_node",
    "describe_result",
    "grounded_insight",
    "about",
    "get_readme_context",
    "run_ask",
]
