from langgraph.graph import END, START, StateGraph

from continum.ExpSuite.stats_inference import SRMInput, detect_srm
from continum.mapMeta import StatSigFetchInput, fetch_statsig_experiment_health
from continum.state import MonitoringState


def fetch_telemetry_node(state: MonitoringState) -> dict:
    """Retrieves pulse metrics and exposure counts from StatSig."""
    experiment_id = state.get("active_experiment_id")
    if not experiment_id:
        return {"missing_inputs": ["active_experiment_id"]}

    telemetry = fetch_statsig_experiment_health(StatSigFetchInput(experiment_id=experiment_id))

    # `fetch_statsig_experiment_health` returns is_live=True even on its offline
    # mock branch, so is_live alone cannot distinguish real telemetry from the
    # STATSIG_API_KEY-absent fallback. The `[MOCK STATSIG]` summary prefix is the
    # reliable signal — surface it as an alert so downstream never mistakes
    # placeholder exposure counts for measured ones.
    is_mock = "[MOCK STATSIG]" in (telemetry.summary or "")
    alerts = []
    if is_mock:
        alerts.append(
            "Telemetry is mock data (STATSIG_API_KEY is not configured): " + telemetry.summary
        )
    elif not telemetry.is_live:
        alerts.append(telemetry.summary)

    update: dict = {"telemetry": telemetry.model_dump(), "guardrail_alerts": alerts}

    # Exposure counts are the SRM test's input. Prefer counts the caller passed
    # explicitly; otherwise take them from telemetry. Note that
    # `fetch_statsig_experiment_health` returns labelled mock counts when
    # STATSIG_API_KEY is unset — `telemetry.is_live` and the `[MOCK STATSIG]`
    # prefix in its summary both stay in state so downstream can see that.
    if not state.get("observed_counts"):
        update["observed_counts"] = [
            telemetry.control_exposures,
            telemetry.treatment_exposures,
        ]

    return update


def check_srm_node(state: MonitoringState) -> dict:
    """Performs Chi-Square goodness-of-fit test for Sample Ratio Mismatch."""
    observed_counts = state.get("observed_counts")
    if not observed_counts or len(observed_counts) < 2:
        return {"missing_inputs": ["observed_counts"]}

    result = detect_srm(
        SRMInput(
            observed_counts=observed_counts,
            expected_ratios=state.get("expected_ratios"),
        )
    )

    alerts = list(state.get("guardrail_alerts") or [])
    if result.has_srm:
        alerts.append(result.summary)

    return {
        "srm_result": result.model_dump(),
        "srm_status": "CRITICAL" if result.has_srm else "HEALTHY",
        "guardrail_alerts": alerts,
    }


builder = StateGraph(MonitoringState)
builder.add_node("fetch_telemetry", fetch_telemetry_node)
builder.add_node("check_srm", check_srm_node)

builder.add_edge(START, "fetch_telemetry")
builder.add_edge("fetch_telemetry", "check_srm")
builder.add_edge("check_srm", END)

monitoring_subgraph = builder.compile()
