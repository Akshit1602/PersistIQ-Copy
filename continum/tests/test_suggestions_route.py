"""The suggestions route must always answer, even with nothing to suggest."""

from continum.userui.routes import suggestions_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.include_router(suggestions_router)
client = TestClient(app)


def test_digital_suggestions_use_frontend_field_keys():
    res = client.get("/api/suggestions/inputs", params={"experiment": "Mobile Nav Redesign"})
    assert res.status_code == 200

    body = res.json()
    assert body["channel"] == "digital"
    assert set(body["fields"]) >= {"baselineIor", "dailyTraffic", "aov"}

    ior = body["fields"]["baselineIor"]
    assert 0 < ior["value"] < 1
    assert ior["confidence"] == "high"
    assert ior["rationale"]  # provenance is what the UI tooltip renders


def test_store_suggestions_cover_the_store_wizard_fields():
    res = client.get(
        "/api/suggestions/inputs",
        params={"experiment": "Dedicated Cashier Staffing Rollout", "channel": "store"},
    )
    assert res.status_code == 200

    body = res.json()
    assert body["channel"] == "store"
    assert set(body["fields"]) >= {"targetStoreCount", "weeklyStoreTraffic", "baselineCvr"}


def test_experiment_is_required():
    assert client.get("/api/suggestions/inputs").status_code == 422
