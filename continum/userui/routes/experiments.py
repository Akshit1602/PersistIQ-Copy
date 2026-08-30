from typing import Any, Dict, List

from fastapi import APIRouter

from continum.mapMeta import StatSigFetchInput, fetch_statsig_experiment_health

router = APIRouter(prefix="/api/experiments", tags=["Experiments & Data Catalog"])


import sqlite3

DB_PATH = "matchview_omnichannel.db"

@router.get("", response_model=List[Dict[str, Any]])
async def list_experiments():
    """
    Returns all cataloged experiments from ecomm_experiments and store_experiments tables.
    """
    experiments = []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Ecomm experiments
        cursor.execute("SELECT experiment_id, name, status, target_metric FROM ecomm_experiments")
        for r in cursor.fetchall():
            experiments.append({
                "experiment_id": r[0],
                "name": r[1],
                "status": (r[2] or "RUNNING").upper(),
                "primary_metric": r[3] or "conversion_rate",
                "sample_size": 15000,
                "srm_status": "HEALTHY",
            })

        # Store experiments
        cursor.execute("SELECT experiment_id, name, status, target_metric FROM store_experiments")
        for r in cursor.fetchall():
            experiments.append({
                "experiment_id": r[0],
                "name": r[1],
                "status": (r[2] or "RUNNING").upper(),
                "primary_metric": r[3] or "basket_size",
                "sample_size": 25000,
                "srm_status": "HEALTHY",
            })

        conn.close()
    except Exception as e:
        print(f"Error querying experiments from DB: {e}")

    return experiments


@router.get("/{experiment_id}/health")
async def get_experiment_health(experiment_id: str):
    """
    Fetches live exposure telemetry and pulse health for an experiment from StatSig.
    """
    res = fetch_statsig_experiment_health(StatSigFetchInput(experiment_id=experiment_id))
    return res.model_dump()
