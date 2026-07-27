from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import requests
from continum.config import settings


class StatSigFetchInput(BaseModel):
    experiment_id: str = Field(..., description="StatSig experiment ID or feature flag key")


class StatSigFetchResult(BaseModel):
    experiment_id: str
    status: str
    control_exposures: int
    treatment_exposures: int
    pulse_metrics: Dict[str, Any]
    is_live: bool
    summary: str


def fetch_statsig_experiment_health(input_data: StatSigFetchInput) -> StatSigFetchResult:
    """
    Retrieves exposure counts and pulse data from StatSig API.
    Falls back gracefully to mock telemetry if STATSIG_API_KEY is not configured.
    """
    if not settings.STATSIG_API_KEY:
        # Graceful fallback mock data for offline/dev testing
        return StatSigFetchResult(
            experiment_id=input_data.experiment_id,
            status="ACTIVE",
            control_exposures=12500,
            treatment_exposures=12480,
            pulse_metrics={"conversion_rate": {"control": 0.102, "treatment": 0.108, "p_value": 0.034}},
            is_live=True,
            summary=f"[MOCK STATSIG] Experiment '{input_data.experiment_id}' is ACTIVE. Control: 12,500, Treatment: 12,480."
        )

    headers = {
        "STATSIG-API-KEY": settings.STATSIG_API_KEY,
        "Content-Type": "application/json"
    }

    url = f"{settings.STATSIG_BASE_URL}/experiments/{input_data.experiment_id}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            payload = response.json().get("data", {})
            return StatSigFetchResult(
                experiment_id=input_data.experiment_id,
                status=payload.get("status", "UNKNOWN"),
                control_exposures=payload.get("target_group_exposures", {}).get("control", 0),
                treatment_exposures=payload.get("target_group_exposures", {}).get("treatment", 0),
                pulse_metrics=payload.get("pulse_results", {}),
                is_live=True,
                summary=f"StatSig live payload retrieved for '{input_data.experiment_id}'."
            )
        else:
            return StatSigFetchResult(
                experiment_id=input_data.experiment_id,
                status="ERROR",
                control_exposures=0,
                treatment_exposures=0,
                pulse_metrics={},
                is_live=False,
                summary=f"StatSig API Error {response.status_code}: {response.text}"
            )
    except Exception as e:
        return StatSigFetchResult(
            experiment_id=input_data.experiment_id,
            status="EXCEPTION",
            control_exposures=0,
            treatment_exposures=0,
            pulse_metrics={},
            is_live=False,
            summary=f"Failed to connect to StatSig API: {str(e)}"
        )