from typing import TypedDict, Annotated, Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


# ==========================================
# Generative UI Artifact Contract
# ==========================================

class UIArtifact(BaseModel):
    """Payload contract for interactive frontend visual components."""
    artifact_id: str
    type: Literal[
        "plotly_chart", 
        "experiment_brief", 
        "srm_alert_card", 
        "stat_results_card", 
        "growth_prediction_card",
        "data_table"
    ]
    title: str
    payload: Dict[str, Any]


# ==========================================
# Domain Pydantic Models
# ==========================================

class MetricDefinition(BaseModel):
    name: str
    table: str
    column: str
    aggregation: str = "SUM"
    description: Optional[str] = None


class SchemaMetadata(BaseModel):
    tables: List[str] = Field(default_factory=list)
    schema_summary: str = ""
    metrics_catalog: Dict[str, MetricDefinition] = Field(default_factory=dict)
    cataloged_experiments: List[Dict[str, Any]] = Field(default_factory=list)


class ExperimentBrief(BaseModel):
    hypothesis: str = ""
    primary_metric: str = ""
    guardrail_metrics: List[str] = Field(default_factory=list)
    target_segment: str = ""
    baseline_conversion_rate: Optional[float] = None
    baseline_variance: Optional[float] = None
    mde: Optional[float] = None
    required_sample_size: Optional[int] = None
    estimated_duration_days: Optional[int] = None


class StatResults(BaseModel):
    experiment_id: str
    control_count: int = 0
    treatment_count: int = 0
    control_mean: float = 0.0
    treatment_mean: float = 0.0
    absolute_lift: float = 0.0
    relative_lift: float = 0.0
    p_value: float = 1.0
    is_stat_sig: bool = False
    srm_p_value: Optional[float] = None
    has_srm: bool = False
    cuped_applied: bool = False


class GrowthPrediction(BaseModel):
    hypothesis_id: str
    metric_name: str
    assumed_lift: float
    projected_quarterly_lift: float
    projected_annual_lift: float
    simulation_bounds: Dict[str, float] = Field(default_factory=dict)


# ==========================================
# Unified LangGraph AgentState
# ==========================================

class AgentState(TypedDict):
    # Message Thread History (reduced via add_messages)
    messages: Annotated[list, add_messages]

    # Active Conversation Context
    active_experiment_id: Optional[str]
    current_intent: Optional[str]

    # Generative UI Artifacts for stream rendering
    ui_artifacts: List[UIArtifact]

    # Human-In-The-Loop (HITL) context
    pending_approval: Optional[Dict[str, Any]]

    # Domain State Containers
    schema_metadata: Optional[SchemaMetadata]
    brief: Optional[ExperimentBrief]
    statsig_experiment_id: Optional[str]
    srm_flag: Optional[bool]
    health_alerts: List[str]
    analysis_results: Optional[StatResults]
    plotly_json: Optional[Dict[str, Any]]
    growth_projection: Optional[GrowthPrediction]
    generated_sql: Optional[str]

    # Execution Warnings and Errors
    errors: List[str]