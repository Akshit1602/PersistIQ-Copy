import sys

from continum.askdata import chart_spec, growth_simulator, sql_engine, visual_generator
from continum.askdata.chart_spec import (
    ChartKind,
    ChartSeries,
    ChartSpec,
    derive_chart_spec,
    is_chartable,
    spec_to_plotly,
    summarize_spec,
)
from continum.askdata.growth_simulator import (
    GrowthSimulationInput,
    GrowthSimulationResult,
    simulate_and_visualize_growth,
)
from continum.askdata.sql_engine import SQLExecutionInput, SQLExecutionResult, execute_sql_query
from continum.askdata.visual_generator import (
    SUPPORTED_CHART_TYPES,
    ChartGeneratorInput,
    ChartGeneratorResult,
    build_growth_forecast_chart,
    build_growth_forecast_spec,
    build_metric_lift_chart,
    build_metric_lift_spec,
    build_srm_distribution_chart,
    build_srm_distribution_spec,
    generate_visualization,
)

# Register AskData case-compatibility aliases in sys.modules
sys.modules["continum.AskData"] = sys.modules[__name__]
sys.modules["continum.AskData.chart_spec"] = chart_spec
sys.modules["continum.AskData.growth_simulator"] = growth_simulator
sys.modules["continum.AskData.sql_engine"] = sql_engine
sys.modules["continum.AskData.visual_generator"] = visual_generator

__all__ = [
    "generate_visualization",
    "build_metric_lift_chart",
    "build_srm_distribution_chart",
    "build_growth_forecast_chart",
    "build_metric_lift_spec",
    "build_srm_distribution_spec",
    "build_growth_forecast_spec",
    "ChartGeneratorInput",
    "ChartGeneratorResult",
    "SUPPORTED_CHART_TYPES",
    "ChartKind",
    "ChartSeries",
    "ChartSpec",
    "derive_chart_spec",
    "is_chartable",
    "spec_to_plotly",
    "summarize_spec",
    "execute_sql_query",
    "SQLExecutionInput",
    "SQLExecutionResult",
    "simulate_and_visualize_growth",
    "GrowthSimulationInput",
    "GrowthSimulationResult",
]
