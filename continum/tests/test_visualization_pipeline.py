"""
Routing assertions for the visualization path.

The failure this guards against is silent: every link between "the user asked
for a chart" and "a chart card appears" can break without raising, and the user
just sees prose. So these tests assert the whole chain a chart travels --
deterministic guard -> graph route -> tool return -> UIArtifact -> JSON the SSE
layer can serialise -- rather than only that a spec-builder returns a spec.

None of it touches an LLM, so it needs no API key.
"""

import json

import pytest
from continum.AskData import ChartGeneratorInput, derive_chart_spec, generate_visualization
from continum.orchestration.subgraphs.askdata_graph import route_after_sql, route_request
from continum.orchestration.tools.subgraph_tools import (
    ask_data_insights,
    ask_data_sql,
    ask_data_visualize,
    run_experiment_analysis_workflow,
)

CHARTABLE_ROWS = [
    {"region": "North", "revenue": 120.5},
    {"region": "South", "revenue": 98.2},
    {"region": "East", "revenue": 143.9},
]

# A literal SELECT stands in for a warehouse table: the assertion is about the
# route the rows take, not about where they came from.
CHARTABLE_QUERY = (
    "SELECT 'North' AS region, 120.5 AS revenue UNION ALL "
    "SELECT 'South', 98.2 UNION ALL SELECT 'East', 143.9"
)


def _chart_artifacts(result: dict) -> list:
    return [a for a in (result.get("ui_artifacts") or []) if a["type"] == "plotly_chart"]


def _assert_renderable(artifact: dict) -> dict:
    """
    An artifact only reaches the UI if it survives `json.dumps` -- chat.py
    serialises it into an SSE frame -- and only renders if it carries a spec
    with at least one populated series.
    """
    json.dumps(artifact)
    spec = artifact["payload"]["chart_spec"]
    assert spec["categories"], "chart has no categories to plot against"
    assert spec["series"], "chart has no series"
    assert any(v is not None for v in spec["series"][0]["values"])
    assert artifact["payload"]["summary"].strip()
    return spec


# ==========================================
# Deterministic guard
# ==========================================


@pytest.mark.parametrize(
    "rows,expected_kind",
    [
        (CHARTABLE_ROWS, "bar"),
        (
            [
                {"week": "2026-01-05", "orders": 210},
                {"week": "2026-01-12", "orders": 245},
            ],
            "line",
        ),
        (
            [
                {"region": "N", "revenue": 120.0, "cost": 90.0},
                {"region": "S", "revenue": 98.0, "cost": 70.0},
            ],
            "grouped_bar",
        ),
        ([{"control": 100, "treatment": 108}], "bar"),
    ],
)
def test_chartable_rows_derive_the_expected_shape(rows, expected_kind):
    spec = derive_chart_spec(rows)
    assert spec is not None
    assert spec.kind == expected_kind


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"total": 42}],  # a single scalar is a sentence, not a chart
        [{"name": "a"}, {"name": "b"}],  # no measure
        [{"g": "A", "v": None}, {"g": "B", "v": None}],  # measure is all null
        [{"g": "A", "flag": True}, {"g": "B", "flag": False}],  # booleans are categories
    ],
)
def test_unchartable_rows_produce_no_spec(rows):
    assert derive_chart_spec(rows) is None


def test_mixed_scale_measures_are_not_forced_onto_one_axis():
    spec = derive_chart_spec(
        [
            {"week": "2026-01-05", "conversion_rate": 0.031, "orders": 210},
            {"week": "2026-01-12", "conversion_rate": 0.036, "orders": 245},
        ]
    )
    assert spec is not None
    assert [s.name for s in spec.series] == ["Conversion Rate"]
    assert any("different scale" in note for note in spec.notes)


def test_truncation_is_reported_rather_than_silent():
    rows = [{"bucket": f"b{i}", "value": i} for i in range(120)]
    spec = derive_chart_spec(rows)
    assert spec is not None
    assert len(spec.categories) == 40
    assert any("first 40 of 120" in note for note in spec.notes)


# ==========================================
# Graph routing
# ==========================================


def test_route_request_prefers_the_branch_whose_inputs_were_supplied():
    assert route_request({"query": "SELECT 1"}) == "run_sql"
    assert route_request({"chart_type": "bar"}) == "render_chart"
    assert route_request({"baseline_monthly_revenue": 1.0}) == "simulate_growth"
    assert route_request({}) == "report_missing"


def test_sql_results_route_on_to_the_auto_chart_terminal():
    assert route_after_sql({"query_results": CHARTABLE_ROWS}) == "auto_chart"


@pytest.mark.parametrize(
    "state",
    [
        {"query_results": CHARTABLE_ROWS, "visualize": False},
        {"query_results": []},
        {"query_results": [{"total": 42}]},
    ],
)
def test_auto_chart_is_skipped_when_it_would_not_help(state):
    assert route_after_sql(state) == "end"


# ==========================================
# End-to-end through the agent tools
# ==========================================


def test_sql_tool_charts_a_chartable_result_without_being_asked():
    result = ask_data_sql.invoke({"query": CHARTABLE_QUERY, "chart_title": "Revenue by Region"})

    assert not result.get("errors")
    artifacts = _chart_artifacts(result)
    assert len(artifacts) == 1, "a chartable SQL result must emit exactly one chart card"

    spec = _assert_renderable(artifacts[0])
    assert spec["categories"] == ["North", "South", "East"]
    assert spec["series"][0]["values"] == [120.5, 98.2, 143.9]


def test_sql_tool_honours_an_explicit_opt_out():
    result = ask_data_sql.invoke({"query": CHARTABLE_QUERY, "visualize": False})
    assert _chart_artifacts(result) == []
    assert result.get("query_results"), "opting out of the chart must not drop the rows"


def test_sql_tool_return_stays_light_enough_for_the_model():
    """Plotly JSON must not ride along into the ToolMessage the model reads."""
    result = ask_data_sql.invoke({"query": CHARTABLE_QUERY})
    assert "plotly_json" not in result


@pytest.mark.parametrize(
    "chart_type,data",
    [
        ("bar", {"categories": ["N", "S"], "values": [1.0, 2.0]}),
        (
            "grouped_bar",
            {"categories": ["N", "S"], "series": [{"name": "Rev", "values": [1.0, 2.0]}]},
        ),
        ("auto", {"rows": CHARTABLE_ROWS}),
        (
            "metric_lift",
            {"control_mean": 100.0, "treatment_mean": 108.0, "ci_lower": 4.0, "ci_upper": 12.0},
        ),
        ("srm_distribution", {"observed_counts": [500, 520], "expected_counts": [510.0, 510.0]}),
        ("growth_forecast", {"p10": 1.0, "p50": 2.0, "p90": 3.0}),
    ],
)
def test_visualize_tool_emits_a_renderable_card_for_every_chart_type(chart_type, data):
    result = ask_data_visualize.invoke({"chart_type": chart_type, "data": data, "title": "T"})
    artifacts = _chart_artifacts(result)
    assert len(artifacts) == 1
    _assert_renderable(artifacts[0])


def test_visualize_tool_reports_unplottable_data_instead_of_drawing_zeroes():
    result = ask_data_visualize.invoke(
        {"chart_type": "bar", "data": {"categories": ["a"], "series": []}, "title": "T"}
    )
    assert _chart_artifacts(result) == []
    assert result.get("errors"), "an unplottable chart request must say why"


def test_growth_forecast_tool_emits_a_chart_card():
    result = ask_data_insights.invoke(
        {"baseline_monthly_revenue": 500000.0, "expected_lift_pct": 0.02}
    )
    artifacts = _chart_artifacts(result)
    assert len(artifacts) == 1
    _assert_renderable(artifacts[0])


def test_analysis_workflow_emits_a_metric_lift_card():
    result = run_experiment_analysis_workflow.invoke(
        {
            "experiment_id": "ci_test_exp",
            "control_mean": 100.0,
            "control_std": 20.0,
            "control_count": 5000,
            "treatment_mean": 108.0,
            "treatment_std": 20.0,
            "treatment_count": 5000,
            "primary_metric": "aov",
        }
    )
    artifacts = _chart_artifacts(result)
    assert len(artifacts) == 1

    spec = _assert_renderable(artifacts[0])
    assert spec["categories"] == ["Control", "Treatment"]
    # The chart must show the means the test actually ran on, not re-derived ones.
    assert spec["series"][0]["values"] == [100.0, 108.0]


def test_unplottable_request_never_yields_a_placeholder_chart():
    """
    The old default branch drew a two-bar chart of zeroes for any unknown type.
    Downstream that is indistinguishable from a real measurement of zero.
    """
    result = generate_visualization(
        ChartGeneratorInput(chart_type="not_a_chart_type", title="T", data={})
    )
    assert result.chart_spec is None
    assert result.plotly_json == {}
    assert "no numeric series" in result.summary
