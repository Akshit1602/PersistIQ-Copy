"""
Renderer-neutral chart specification, plus deterministic derivation from rows.

Plotly JSON is a rendering detail of one library. MatchView's frontend draws its
charts as inline SVG and carries no charting dependency, and a Plotly figure is
several KB of layout noise -- far too heavy to round-trip through a tool result
that the LLM has to read. So every chart travels as a `ChartSpec`: categories
plus named numeric series, a few hundred bytes. `spec_to_plotly` derives the
Plotly figure from it for callers (notebooks, exports) that still want one.

`derive_chart_spec` is the deterministic guard on the auto-visualization path.
It returns None -- never a fabricated or empty chart -- when the rows have
nothing worth plotting, so the caller can fall back to text instead of rendering
an axis with no data on it.
"""

import logging
import re
from typing import Any, Dict, List, Literal, Optional, Sequence

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ChartKind = Literal["bar", "grouped_bar", "line", "area", "pie", "scatter"]
ValueFormat = Literal["number", "currency", "percent"]

# A chart with more bars than this is unreadable at card width, and a legend
# with more entries than this is unreadable at any width. Both are truncated
# rather than dropped, and the truncation is recorded in `spec.notes` so the
# reader is never silently shown a partial picture.
MAX_CATEGORIES = 40
MAX_SERIES = 6

# Identifier-ish columns are numeric but meaningless to plot. Dropped only when
# a real measure is also present, so a table of nothing but ids still charts.
_ID_COLUMN = re.compile(r"^(id|index|row_?num|.*_id|.*_key|.*_code)$", re.IGNORECASE)
_TEMPORAL_COLUMN = re.compile(
    r"(date|time|day|week|month|quarter|year|period|ts|timestamp)", re.IGNORECASE
)
_MONEY_COLUMN = re.compile(
    r"(revenue|sales|gmv|aov|cost|profit|margin|price|spend|value_usd)", re.IGNORECASE
)
_RATE_COLUMN = re.compile(r"(rate|pct|percent|ratio|share|conversion|ctr|cvr)", re.IGNORECASE)

# Series colours are hints only -- the frontend applies its own token palette by
# series index. They exist so a Plotly render of the same spec looks deliberate.
SERIES_COLORS = ["#4C6FFF", "#00B389", "#F5A623", "#9B51E0", "#EB5757", "#2D9CDB"]


class ChartSeries(BaseModel):
    """One named line/bar group. `values` is index-aligned with `categories`."""

    name: str
    values: List[Optional[float]]
    color: Optional[str] = None
    # Symmetric half-width error bars, index-aligned with `values`. Used for
    # confidence intervals on estimated effects.
    error: Optional[List[Optional[float]]] = None


class ChartSpec(BaseModel):
    kind: ChartKind = "bar"
    title: str = "Chart"
    categories: List[str] = Field(default_factory=list)
    series: List[ChartSeries] = Field(default_factory=list)
    x_title: str = ""
    y_title: str = ""
    value_format: ValueFormat = "number"
    # Caveats the reader needs in order to trust the picture (truncation,
    # provenance). Rendered under the chart, never as a data label.
    notes: List[str] = Field(default_factory=list)


# ==========================================
# Value coercion & column classification
# ==========================================


def _coerce_number(value: Any) -> Optional[float]:
    """
    Returns `value` as a float, or None when it is not a plottable number.

    Booleans are excluded deliberately: `True` is numerically 1 but a boolean
    column is a category, and charting it as a measure produces a bar of height
    1 that means nothing. Numeric strings ARE accepted, because warehouse
    drivers routinely return DECIMAL columns as strings.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("$", "").rstrip("%")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _column_names(rows: Sequence[Dict[str, Any]], columns: Optional[Sequence[str]]) -> List[str]:
    if columns:
        return list(columns)
    seen: List[str] = []
    for row in rows:
        for key in row:
            if key not in seen:
                seen.append(key)
    return seen


def _is_numeric_column(rows: Sequence[Dict[str, Any]], column: str) -> bool:
    """
    True when every populated cell in the column is a number and at least one
    cell is populated. "Mostly numeric" is treated as non-numeric on purpose --
    a column with stray text is a label column with dirty data, and plotting it
    would silently drop the rows that did not parse.
    """
    saw_value = False
    for row in rows:
        raw = row.get(column)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        if _coerce_number(raw) is None:
            return False
        saw_value = True
    return saw_value


def _looks_temporal(column: str, values: Sequence[Any]) -> bool:
    if _TEMPORAL_COLUMN.search(column):
        return True
    # ISO-ish dates in the label column, e.g. '2026-08-24' or '2026/08'.
    pattern = re.compile(r"^\d{4}[-/]\d{1,2}([-/]\d{1,2})?")
    populated = [str(v) for v in values if v is not None]
    return bool(populated) and all(pattern.match(v) for v in populated)


# Two measures may share a y-axis while their typical magnitudes stay within
# this factor of each other. Beyond it the smaller one is visually zero.
_SHARED_AXIS_RATIO = 50.0


def _typical_magnitude(rows: Sequence[Dict[str, Any]], column: str) -> float:
    """Largest absolute value in the column, ignoring nulls and exact zeroes."""
    magnitudes = [
        abs(n)
        for n in (_coerce_number(row.get(column)) for row in rows)
        if n is not None and n != 0
    ]
    return max(magnitudes) if magnitudes else 0.0


def _comparable_measures(rows: Sequence[Dict[str, Any]], measures: Sequence[str]) -> List[str]:
    """
    The measures that can honestly share one y-axis with the first one. An
    all-zero column has no magnitude to compare and is kept, since plotting it
    misleads no one.
    """
    reference = _typical_magnitude(rows, measures[0])
    if reference == 0:
        return list(measures)

    keep = []
    for column in measures:
        magnitude = _typical_magnitude(rows, column)
        ratio = max(magnitude, reference) / min(magnitude, reference) if magnitude else 1.0
        if ratio <= _SHARED_AXIS_RATIO:
            keep.append(column)
    return keep


def _value_format_for(columns: Sequence[str]) -> ValueFormat:
    if columns and all(_MONEY_COLUMN.search(c) for c in columns):
        return "currency"
    if columns and all(_RATE_COLUMN.search(c) for c in columns):
        return "percent"
    return "number"


def _humanize(column: str) -> str:
    return column.replace("_", " ").strip().title()


# ==========================================
# Derivation from result rows
# ==========================================


def derive_chart_spec(
    rows: Sequence[Dict[str, Any]],
    columns: Optional[Sequence[str]] = None,
    title: str = "Query Result",
    preferred_kind: Optional[ChartKind] = None,
) -> Optional[ChartSpec]:
    """
    Builds a chart from tabular rows, or returns None when a chart would not
    help. This is the deterministic half of the auto-visualization decision --
    no model is consulted, so the same rows always produce the same answer, and
    a "why is there no chart" question always has a checkable reason.

    None is returned when:
      * there are no rows;
      * no column holds numbers (nothing to measure);
      * the result is a single scalar (one row, one measure -- a sentence, not
        a chart).
    """
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        logger.info("derive_chart_spec: no rows to plot")
        return None

    all_columns = _column_names(rows, columns)
    numeric = [c for c in all_columns if _is_numeric_column(rows, c)]
    labels = [c for c in all_columns if c not in numeric]

    # Ids are numeric but not measures. Keep them only if nothing else is.
    measures = [c for c in numeric if not _ID_COLUMN.match(c)] or numeric

    if not measures:
        logger.info("derive_chart_spec: no numeric column in %s -- skipping chart", all_columns)
        return None

    notes: List[str] = []

    # Single row: the row itself is the comparison, so the measures become the
    # categories. One measure on one row is a scalar and gets no chart.
    if len(rows) == 1:
        if len(measures) < 2:
            logger.info("derive_chart_spec: single scalar result -- skipping chart")
            return None
        row = rows[0]
        values = [_coerce_number(row.get(c)) for c in measures[:MAX_CATEGORIES]]
        return ChartSpec(
            kind=preferred_kind or "bar",
            title=title,
            categories=[_humanize(c) for c in measures[:MAX_CATEGORIES]],
            series=[ChartSeries(name="Value", values=values, color=SERIES_COLORS[0])],
            y_title="Value",
            value_format=_value_format_for(measures),
            notes=notes,
        )

    # An id column is a poor measure but a good label — it is what distinguishes
    # the rows. Falling through to positional labels instead would throw away
    # the only thing naming each bar.
    id_columns = [c for c in numeric if c not in measures]
    label_column = labels[0] if labels else (id_columns[0] if id_columns else None)
    plotted_rows = list(rows)
    if len(plotted_rows) > MAX_CATEGORIES:
        notes.append(f"Showing the first {MAX_CATEGORIES} of {len(rows)} rows.")
        plotted_rows = plotted_rows[:MAX_CATEGORIES]

    if label_column is not None:
        categories = [str(row.get(label_column, "")) for row in plotted_rows]
    else:
        categories = [str(i + 1) for i in range(len(plotted_rows))]

    # Measures on wildly different scales cannot share a y-axis: a conversion
    # rate of 0.03 plotted beside an order count of 245 flattens to the axis and
    # reads as zero. Keep the first measure and only its comparable companions,
    # and name what was left off rather than dropping it silently.
    comparable = _comparable_measures(plotted_rows, measures)
    if len(comparable) < len(measures):
        excluded = ", ".join(_humanize(c) for c in measures if c not in comparable)
        notes.append(f"Charted separately (different scale): {excluded}.")

    plotted_measures = comparable[:MAX_SERIES]
    if len(comparable) > MAX_SERIES:
        dropped = ", ".join(_humanize(c) for c in comparable[MAX_SERIES:])
        notes.append(f"Not charted: {dropped}.")

    series = [
        ChartSeries(
            name=_humanize(column),
            values=[_coerce_number(row.get(column)) for row in plotted_rows],
            color=SERIES_COLORS[i % len(SERIES_COLORS)],
        )
        for i, column in enumerate(plotted_measures)
    ]

    if preferred_kind:
        kind: ChartKind = preferred_kind
    elif label_column is not None and _looks_temporal(label_column, categories):
        kind = "line"
    elif len(series) > 1:
        kind = "grouped_bar"
    else:
        kind = "bar"

    return ChartSpec(
        kind=kind,
        title=title,
        categories=categories,
        series=series,
        x_title=_humanize(label_column) if label_column else "",
        y_title=_humanize(plotted_measures[0]) if len(plotted_measures) == 1 else "Value",
        value_format=_value_format_for(plotted_measures),
        notes=notes,
    )


def is_chartable(rows: Sequence[Dict[str, Any]], columns: Optional[Sequence[str]] = None) -> bool:
    """Cheap predicate form of `derive_chart_spec` for routing decisions."""
    return derive_chart_spec(rows, columns) is not None


# ==========================================
# Rendering & description
# ==========================================


def _format_value(value: Optional[float], value_format: ValueFormat) -> str:
    if value is None:
        return "n/a"
    if value_format == "currency":
        return f"${value:,.2f}"
    if value_format == "percent":
        # Warehouse rate columns arrive either as 0-1 fractions or as 0-100
        # percentages. Treat <= 1 as a fraction, which is the common case.
        return f"{value * 100:.2f}%" if abs(value) <= 1 else f"{value:.2f}%"
    if abs(value) < 1 and value != 0:
        return f"{value:.4f}"
    return f"{value:,.2f}"


def summarize_spec(spec: ChartSpec) -> str:
    """
    One sentence naming what the chart shows and its extremes, so the answer
    still carries the finding for a reader who cannot see the picture.
    """
    if not spec.series or not spec.categories:
        return f"{spec.title}: no data points to plot."

    primary = spec.series[0]
    pairs = [
        (label, value) for label, value in zip(spec.categories, primary.values) if value is not None
    ]
    if not pairs:
        return f"{spec.title}: no data points to plot."

    high_label, high_value = max(pairs, key=lambda p: p[1])
    low_label, low_value = min(pairs, key=lambda p: p[1])
    series_note = f" across {len(spec.series)} series" if len(spec.series) > 1 else ""
    return (
        f"{spec.title}: {primary.name} over {len(pairs)} categories{series_note}. "
        f"Highest {high_label} at {_format_value(high_value, spec.value_format)}, "
        f"lowest {low_label} at {_format_value(low_value, spec.value_format)}."
    )


def spec_to_plotly(spec: ChartSpec) -> Dict[str, Any]:
    """
    Renders a ChartSpec as Plotly figure JSON. Kept for exports and notebooks;
    the MatchView frontend renders `ChartSpec` directly and never reads this.
    """
    import json

    import plotly.graph_objects as go

    traces: List[Any] = []

    if spec.kind == "pie":
        primary = spec.series[0] if spec.series else ChartSeries(name="Value", values=[])
        traces.append(go.Pie(labels=spec.categories, values=primary.values))
    else:
        for index, series in enumerate(spec.series):
            color = series.color or SERIES_COLORS[index % len(SERIES_COLORS)]
            error_y = (
                dict(type="data", array=[e or 0.0 for e in series.error], visible=True)
                if series.error
                else None
            )
            if spec.kind in ("line", "area", "scatter"):
                traces.append(
                    go.Scatter(
                        name=series.name,
                        x=spec.categories,
                        y=series.values,
                        mode="markers" if spec.kind == "scatter" else "lines+markers",
                        fill="tozeroy" if spec.kind == "area" else None,
                        line=dict(color=color),
                        error_y=error_y,
                    )
                )
            else:
                traces.append(
                    go.Bar(
                        name=series.name,
                        x=spec.categories,
                        y=series.values,
                        marker_color=color,
                        error_y=error_y,
                    )
                )

    figure = go.Figure(data=traces)
    figure.update_layout(
        title=spec.title,
        xaxis_title=spec.x_title,
        yaxis_title=spec.y_title,
        barmode="group" if spec.kind == "grouped_bar" else "relative",
        template="plotly_white",
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return json.loads(figure.to_json())
