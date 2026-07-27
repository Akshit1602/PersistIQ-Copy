from typing import Optional
from pydantic import BaseModel, Field
from continum.ExpSuite.causal.methods import calculate_diff_in_diff, DiDInput, DiDResult
from continum.ExpSuite.causal.forecasting import run_monte_carlo_forecast, ForecastInput, ForecastResult


class CausalAnalysisInput(BaseModel):
    analysis_type: str = Field("diff_in_diff", description="Type of observational analysis: 'diff_in_diff' or 'forecast'")
    did_input: Optional[DiDInput] = None
    forecast_input: Optional[ForecastInput] = None


class CausalAnalysisResult(BaseModel):
    analysis_type: str
    did_result: Optional[DiDResult] = None
    forecast_result: Optional[ForecastResult] = None
    summary: str


def run_causal_engine(input_data: CausalAnalysisInput) -> CausalAnalysisResult:
    """
    Coordinates observational causal analysis and predictive forecasting workflows.
    """
    if input_data.analysis_type == "diff_in_diff" and input_data.did_input:
        did_res = calculate_diff_in_diff(input_data.did_input)
        return CausalAnalysisResult(
            analysis_type="diff_in_diff",
            did_result=did_res,
            summary=did_res.summary
        )
    elif input_data.analysis_type == "forecast" and input_data.forecast_input:
        forecast_res = run_monte_carlo_forecast(input_data.forecast_input)
        return CausalAnalysisResult(
            analysis_type="forecast",
            forecast_result=forecast_res,
            summary=forecast_res.summary
        )
    else:
        return CausalAnalysisResult(
            analysis_type=input_data.analysis_type,
            summary="Invalid or incomplete parameters provided for causal engine execution."
        )