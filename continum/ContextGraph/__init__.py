"""ContextGraph — the knowledge / context layer.

In constant communication with every end module (AskData nodes, ExpSuite runs),
it tracks user queries and module outputs and builds a knowledge graph starting
at the dataset level. Folds the former ``datastore/`` (knowledge graph, cross-
experiment memory, semantic layer, lineage, state, experiment registry,
inspectors) and ``insights/`` (insight bus, patterns, session).

Currently emulated on the same DuckDB property-graph + persistent stores the
datastore used; an optional LLM layer summarises/links nodes.
"""

from .experiment_registry import (
    add_experiment,
    experiment_exists,
    list_registry,
    load_registry,
)
from .insight_bus import (
    Insight,
    InsightBus,
    InsightSeverity,
    InsightType,
    get_bus,
    publish_next_steps,
    reset_bus,
)
from .inspect import inspect, inspect_all, print_inspection
from .knowledge_graph import EDGE_TYPES, NODE_TYPES, KnowledgeGraph
from .lineage import ExecutionRegistry, LineageRecord
from .memory import CrossExperimentMemory, get_memory
from .narrative import get_narrative
from .patterns import ExperimentPrior, Pattern, PatternMiner, get_miner
from .semantic_layer import (
    DIMENSION_CATALOG,
    METRIC_REGISTRY,
    Dimension,
    Metric,
)
from .session import (
    ExperimentSession,
    Recommendation,
    get_session,
    new_session,
    set_session,
)
from .stores import ContinumState, ExecutionMemory, OrganisationalMemory

__all__ = [
    # knowledge graph
    "KnowledgeGraph",
    "NODE_TYPES",
    "EDGE_TYPES",
    # memory
    "CrossExperimentMemory",
    "get_memory",
    # narrative
    "get_narrative",
    # state
    "ContinumState",
    "ExecutionMemory",
    "OrganisationalMemory",
    # lineage
    "LineageRecord",
    "ExecutionRegistry",
    # inspectors
    "inspect",
    "inspect_all",
    "print_inspection",
    # experiment registry
    "load_registry",
    "list_registry",
    "experiment_exists",
    "add_experiment",
    # semantic layer
    "METRIC_REGISTRY",
    "DIMENSION_CATALOG",
    "Metric",
    "Dimension",
    # insight bus
    "InsightType",
    "InsightSeverity",
    "Insight",
    "InsightBus",
    "get_bus",
    "reset_bus",
    "publish_next_steps",
    # patterns
    "Pattern",
    "ExperimentPrior",
    "PatternMiner",
    "get_miner",
    # session
    "ExperimentSession",
    "Recommendation",
    "get_session",
    "new_session",
    "set_session",
]
