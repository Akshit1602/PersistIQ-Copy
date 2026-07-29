from mcp.server.fastmcp import FastMCP

from continum.askdata import SQLExecutionInput, execute_sql_query
from continum.ExpSuite.planning import (
    OpportunitySizingInput,
    PowerCalcInput,
    calculate_opportunity_size,
    calculate_power,
)

# Import pure functions and input models from ExpSuite, mapMeta, and askdata
from continum.ExpSuite.stats_inference import (
    SRMInput,
    StatTestInput,
    calculate_hypothesis_test,
    detect_srm,
)
from continum.mapMeta import StatSigFetchInput, fetch_statsig_experiment_health

# Initialize FastMCP Server
mcp_server = FastMCP(
    name="Continum Experimentation Engine",
    instructions="Standardized MCP Server exposing statistical inference, experiment planning, SQL execution, and StatSig health tools.",
)


# ==========================================
# MCP Tool Declarations
# ==========================================


@mcp_server.tool()
def check_sample_ratio_mismatch(
    control_count: int, treatment_count: int, expected_ratio: float = 0.5
) -> str:
    """Check for Sample Ratio Mismatch (SRM) across experiment variants using Chi-Square goodness-of-fit."""
    res = detect_srm(
        SRMInput(
            observed_counts=[control_count, treatment_count],
            expected_ratios=[expected_ratio, 1.0 - expected_ratio],
        )
    )
    return res.summary


@mcp_server.tool()
def calculate_sample_size_and_power(
    baseline_rate: float, mde_relative: float, alpha: float = 0.05, power: float = 0.80
) -> str:
    """Calculate required sample size per variant and total test duration given baseline rate and relative MDE."""
    res = calculate_power(
        PowerCalcInput(
            baseline_rate=baseline_rate, mde_relative=mde_relative, alpha=alpha, power=power
        )
    )
    return res.summary


@mcp_server.tool()
def calculate_opportunity_sizing(
    annual_traffic: int,
    baseline_conversion_rate: float,
    average_order_value: float,
    assumed_relative_lift: float = 0.02,
) -> str:
    """Estimate annual and quarterly incremental conversions and revenue impact for a target lift hypothesis."""
    res = calculate_opportunity_size(
        OpportunitySizingInput(
            annual_traffic=annual_traffic,
            baseline_conversion_rate=baseline_conversion_rate,
            average_order_value=average_order_value,
            assumed_relative_lift=assumed_relative_lift,
        )
    )
    return res.summary


@mcp_server.tool()
def run_hypothesis_test(
    control_mean: float,
    control_std: float,
    control_count: int,
    treatment_mean: float,
    treatment_std: float,
    treatment_count: int,
) -> str:
    """Compute Welch's t-test / Z-test, confidence intervals, and relative lift between Control and Treatment."""
    res = calculate_hypothesis_test(
        StatTestInput(
            control_mean=control_mean,
            control_std=control_std,
            control_count=control_count,
            treatment_mean=treatment_mean,
            treatment_std=treatment_std,
            treatment_count=treatment_count,
        )
    )
    return res.summary


@mcp_server.tool()
def fetch_statsig_experiment_health(experiment_id: str) -> str:
    """Retrieve live StatSig pulse telemetry and variant exposure health for an active experiment."""
    res = fetch_statsig_experiment_health(StatSigFetchInput(experiment_id=experiment_id))
    return res.summary


@mcp_server.tool()
def execute_read_only_sql(sql_query: str) -> str:
    """Execute a read-only SELECT query against the warehouse database."""
    res = execute_sql_query(SQLExecutionInput(query=sql_query))
    return res.summary


def start_mcp_server():
    """CLI entry point to launch the FastMCP server."""
    mcp_server.run()


if __name__ == "__main__":
    start_mcp_server()
