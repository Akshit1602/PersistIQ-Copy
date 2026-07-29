from langchain_core.tools import tool

from continum.orchestration.subgraphs import (
    analysis_subgraph,
    askdata_subgraph,
    ingestion_subgraph,
    monitoring_subgraph,
    planning_subgraph,
)


@tool("run_ingestion_workflow")
def run_ingestion_workflow() -> dict:
    """Scan database schema and catalog existing experiments."""
    return ingestion_subgraph.invoke({})


@tool("run_experiment_planning_workflow")
def run_experiment_planning_workflow(hypothesis: str) -> dict:
    """Generate experiment brief, opportunity sizing, power calculations, and traffic splits."""
    initial_state = {"messages": [{"role": "user", "content": hypothesis}]}
    return planning_subgraph.invoke(initial_state)


@tool("run_health_monitoring_workflow")
def run_health_monitoring_workflow(experiment_id: str) -> dict:
    """Fetch StatSig pulse data and run SRM health checks."""
    initial_state = {"active_experiment_id": experiment_id}
    return monitoring_subgraph.invoke(initial_state)


@tool("run_experiment_analysis_workflow")
def run_experiment_analysis_workflow(experiment_id: str) -> dict:
    """Apply CUPED, run hypothesis testing, analyze segments, compute ROI, and generate Plotly charts."""
    initial_state = {"active_experiment_id": experiment_id}
    return analysis_subgraph.invoke(initial_state)


@tool("run_askdata_workflow")
def run_askdata_workflow(query: str) -> dict:
    """Execute text-to-SQL database queries or run Monte Carlo growth predictions."""
    initial_state = {"messages": [{"role": "user", "content": query}]}
    return askdata_subgraph.invoke(initial_state)


subgraph_tools = [
    run_ingestion_workflow,
    run_experiment_planning_workflow,
    run_health_monitoring_workflow,
    run_experiment_analysis_workflow,
    run_askdata_workflow,
]
