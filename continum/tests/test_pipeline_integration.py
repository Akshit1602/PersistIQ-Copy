"""
End-to-end test of the experiment-analysis pipeline, exercised the same way
the agent does: through the `run_experiment_analysis_workflow` tool, not by
calling ExpSuite functions directly. This is the real path a user's request
travels — CUPED -> hypothesis test -> DiD -> ROI framing -> chart — and none
of it touches an LLM, so it needs no API key.
"""

from continum.orchestration.subgraphs.analysis_graph import analysis_subgraph
from continum.orchestration.tools.subgraph_tools import run_experiment_analysis_workflow

# analyze_segments_node has no implementation to run (segment analysis was
# removed upstream) and reports that on every pass rather than staying silent
# about it -- see analysis_graph.py. That is by design, so tests assert this
# exact, single error rather than "no errors".
_SEGMENT_NOT_IMPLEMENTED = (
    "Segment analysis is not implemented: no backend function is wired "
    "for heterogeneous treatment effects."
)


def test_analysis_workflow_runs_hypothesis_test_end_to_end():
    result = run_experiment_analysis_workflow.invoke(
        {
            "experiment_id": "ci_test_exp",
            "control_mean": 100.0,
            "control_std": 20.0,
            "control_count": 5000,
            "treatment_mean": 108.0,
            "treatment_std": 20.0,
            "treatment_count": 5000,
            "primary_metric": "conversion_rate",
        }
    )

    assert not result.get("missing_inputs")
    assert result.get("errors") == [_SEGMENT_NOT_IMPLEMENTED]

    stat = result["stat_result"]
    assert 0.0 <= stat["p_value"] <= 1.0
    assert stat["absolute_lift"] > 0

    assert result["roi_summary"]["absolute_lift"] == stat["absolute_lift"]

    # The chart leaves the tool as a UIArtifact, not as raw Plotly JSON: only an
    # artifact reaches the SSE stream and renders as a card, and the Plotly
    # figure is stripped so it does not bloat the model's context. See
    # test_visualization_pipeline.py for the full chart contract.
    charts = [a for a in result["ui_artifacts"] if a["type"] == "plotly_chart"]
    assert len(charts) == 1
    assert charts[0]["payload"]["chart_spec"]["series"][0]["values"] == [100.0, 108.0]


def test_analysis_workflow_reports_missing_inputs_instead_of_guessing():
    # The tool wrapper declares these fields required, so a caller can't omit
    # them through that interface -- invoke the subgraph directly (as the
    # tool itself does) to exercise run_stats_node's own guard when a field
    # is genuinely absent from state, e.g. a future caller that isn't the tool.
    result = analysis_subgraph.invoke(
        {
            "messages": [],
            "active_experiment_id": "ci_test_exp",
            "primary_metric": "",
            "use_cuped": False,
            "control_mean": 100.0,
            "control_std": 20.0,
            "control_count": 5000,
            # treatment_mean/std/count deliberately absent.
        }
    )
    assert "treatment_mean" in result["missing_inputs"]
    assert "stat_result" not in result


def test_analysis_workflow_runs_diff_in_diff_when_pre_post_means_are_supplied():
    result = run_experiment_analysis_workflow.invoke(
        {
            "experiment_id": "ci_test_exp",
            "control_mean": 100.0,
            "control_std": 20.0,
            "control_count": 5000,
            "treatment_mean": 108.0,
            "treatment_std": 20.0,
            "treatment_count": 5000,
            "control_pre": 90.0,
            "control_post": 95.0,
            "treatment_pre": 90.0,
            "treatment_post": 115.0,
        }
    )
    causal = result["causal_result"]
    assert causal["did_effect"] > 0
    assert 0.0 <= causal["p_value"] <= 1.0
