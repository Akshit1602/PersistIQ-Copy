from typing import Any, Dict

from fastapi import APIRouter, Query

from continum.mapMeta import CHANNELS, get_baseline_profile

router = APIRouter(prefix="/api/suggestions", tags=["Input Suggestions"])

# Confidence the UI uses to decide pre-fill vs. click-to-apply. Everything the
# profiler returns is derived from the experiment's own data, so it is high;
# weaker sources (project history, industry benchmarks) are ranked client-side.
_DATASET_CONFIDENCE = "high"


@router.get("/inputs")
async def suggest_inputs(
    experiment: str = Query(..., description="MatchView experiment name"),
    channel: str = Query("digital", description=f"One of: {', '.join(CHANNELS)}"),
) -> Dict[str, Any]:
    """Baseline input values derived from the data behind an experiment.

    Keys under ``fields`` are frontend form field keys, so the client can apply
    them without a translation table. An unknown experiment returns an empty
    ``fields`` map with a 200 — a missing profile is a normal outcome and must
    degrade to the client's own suggestions rather than break the form.
    """
    profile = get_baseline_profile(experiment, channel)

    return {
        "experiment": experiment,
        "channel": profile.channel,
        "source": profile.source,
        "as_of": profile.as_of,
        "experiment_match": profile.experiment_match,
        "fields": {
            key: {
                "value": detail.value,
                "source": detail.source,
                "confidence": _DATASET_CONFIDENCE,
                "rationale": detail.rationale,
                "row_count": detail.row_count,
                "as_of": detail.as_of,
            }
            for key, detail in profile.fields.items()
        },
    }
