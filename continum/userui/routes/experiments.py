from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from continum.mapMeta import scan_database_schema, fetch_statsig_experiment_health, StatSigFetchInput

router = APIRouter(prefix="/api/experiments", tags=["Experiments & Data Catalog"])


@router.get("", response_model=List[Dict[str, Any]])
async def list_experiments():
    """
    Returns all cataloged experiments for the MatchView Hub view and Header selector.
    """
    schema_meta = scan_database_schema()
    
    # Return discovered or mock experiments
    experiments = [
        {
            "experiment_id": "exp_checkout_redesign",
            "name": "Checkout Flow Redesign v2",
            "status": "RUNNING",
            "primary_metric": "conversion_rate",
            "sample_size": 24980,
            "srm_status": "HEALTHY"
        },
        {
            "experiment_id": "exp_cart_cross_sell_v1",
            "name": "Cart Page Cross-Sell Recommendations",
            "status": "COMPLETED",
            "primary_metric": "average_order_value",
            "sample_size": 30000,
            "srm_status": "HEALTHY"
        }
    ]
    return experiments


@router.get("/{experiment_id}/health")
async def get_experiment_health(experiment_id: str):
    """
    Fetches live exposure telemetry and pulse health for an experiment from StatSig.
    """
    res = fetch_statsig_experiment_health(StatSigFetchInput(experiment_id=experiment_id))
    return res.model_dump()