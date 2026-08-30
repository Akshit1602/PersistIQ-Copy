from langgraph.graph import END, START, StateGraph

from continum.ExpSuite.planning import (
    MetricPlannerInput,
    OpportunitySizingInput,
    PowerCalcInput,
    TrafficBalanceInput,
    calculate_opportunity_size,
    calculate_power,
    calculate_traffic_balance,
    plan_experiment_metrics,
)
from continum.state import ExperimentBrief, MetricDefinition, PlanningState


def _supplied(**kwargs) -> dict:
    """
    Drops keys the caller did not supply so each ExpSuite input model applies its
    own declared default. Never substitutes a value of our own — an absent
    required field surfaces through `missing_inputs` instead.
    """
    return {key: value for key, value in kwargs.items() if value is not None}


def _missing(state: PlanningState, *names: str) -> list:
    return [name for name in names if state.get(name) is None]


def metric_planner_node(state: PlanningState) -> dict:
    """Selects primary, secondary, and guardrail metrics."""
    absent = _missing(state, "primary_metric")
    if absent:
        return {"missing_inputs": absent}

    result = plan_experiment_metrics(
        MetricPlannerInput(
            **_supplied(
                primary_metric=state["primary_metric"],
                retail_domain=state.get("retail_domain"),
            )
        )
    )
    return {"metric_plan_result": result.model_dump()}


def opportunity_sizing_node(state: PlanningState) -> dict:
    """Calculates historical baseline rates and revenue potential."""
    absent = _missing(state, "annual_traffic", "baseline_rate", "average_order_value")
    if absent:
        return {"missing_inputs": absent}

    result = calculate_opportunity_size(
        OpportunitySizingInput(
            **_supplied(
                annual_traffic=state["annual_traffic"],
                baseline_conversion_rate=state["baseline_rate"],
                average_order_value=state["average_order_value"],
                assumed_relative_lift=state.get("assumed_relative_lift"),
            )
        )
    )
    return {"opportunity_result": result.model_dump()}


def power_calculator_node(state: PlanningState) -> dict:
    """Calculates required sample size and test duration."""
    absent = _missing(state, "baseline_rate", "mde_relative")
    if absent:
        return {"missing_inputs": absent}

    result = calculate_power(
        PowerCalcInput(
            **_supplied(
                baseline_rate=state["baseline_rate"],
                mde_relative=state["mde_relative"],
                daily_traffic=state.get("daily_traffic"),
                num_variants=state.get("num_variants"),
            )
        )
    )
    return {"power_result": result.model_dump()}


def traffic_balance_node(state: PlanningState) -> dict:
    """Computes traffic split ratios between control and treatment variants."""
    result = calculate_traffic_balance(
        TrafficBalanceInput(
            **_supplied(
                num_variants=state.get("num_variants"),
                control_split=state.get("control_split"),
            )
        )
    )
    return {"traffic_balance_result": result.model_dump()}


def brief_generator_node(state: PlanningState) -> dict:
    """
    Assembles the experiment brief from computed results. Runs last, because
    every field it needs is produced by an upstream node — `ExperimentBrief`
    requires experiment_id, hypothesis, primary_metric, target_mde,
    baseline_rate, and required_sample_size, so it cannot be built incrementally
    from an empty instance.
    """
    power = state.get("power_result")
    metric_plan = state.get("metric_plan_result")
    if not power or not metric_plan:
        return {
            "errors": [
                "Cannot assemble brief: "
                f"power_result={'set' if power else 'missing'}, "
                f"metric_plan_result={'set' if metric_plan else 'missing'}."
            ]
        }

    messages = state.get("messages") or []
    hypothesis = ""
    if messages:
        last = messages[-1]
        hypothesis = getattr(last, "content", None) or (
            last.get("content", "") if isinstance(last, dict) else ""
        )

    balance = state.get("traffic_balance_result") or {}
    brief = ExperimentBrief(
        experiment_id=state.get("active_experiment_id") or "",
        hypothesis=hypothesis,
        primary_metric=MetricDefinition(
            name=metric_plan["primary_metric"],
            table="",
            column=metric_plan["primary_metric"],
        ),
        guardrails=[
            MetricDefinition(name=name, table="", column=name)
            for name in metric_plan.get("recommended_guardrails", [])
        ],
        target_mde=power["mde_relative"],
        baseline_rate=state["baseline_rate"],
        required_sample_size=power["sample_size_per_variant"],
        **_supplied(traffic_split=balance.get("variant_allocations")),
    )
    return {"experiment_brief": brief}


builder = StateGraph(PlanningState)
builder.add_node("plan_metrics", metric_planner_node)
builder.add_node("size_opportunity", opportunity_sizing_node)
builder.add_node("calculate_power", power_calculator_node)
builder.add_node("balance_traffic", traffic_balance_node)
builder.add_node("generate_brief", brief_generator_node)

# Ordered by data dependency: metrics and sizing feed the power calculation,
# and the brief can only be assembled once all of them have run.
builder.add_edge(START, "plan_metrics")
builder.add_edge("plan_metrics", "size_opportunity")
builder.add_edge("size_opportunity", "calculate_power")
builder.add_edge("calculate_power", "balance_traffic")
builder.add_edge("balance_traffic", "generate_brief")
builder.add_edge("generate_brief", END)

planning_subgraph = builder.compile()
