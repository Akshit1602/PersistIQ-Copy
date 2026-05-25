from __future__ import annotations

import json
import threading

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def synthetic_db():
    import duckdb, pandas as pd, numpy as np

    db = duckdb.connect(":memory:")
    rng = np.random.default_rng(42)
    n   = 2000

    # silver_inquiries
    df_inq = pd.DataFrame({
        "inquiry_id":       range(n),
        "buyer_id":         rng.integers(0, 500, n),
        "created_at":       pd.date_range("2024-01-01", periods=n, freq="2h"),
        "variant":          rng.choice(["control", "treatment"], n),
        "converted_to_order": rng.choice([0, 1], n, p=[0.82, 0.18]),
        "order_value":      rng.uniform(1000, 8000, n),
        "account_segment":  rng.choice(["Core", "Growth", "Enterprise"], n),
        "platform":         rng.choice(["web", "mobile"], n),
        "experiment_name":  "test_exp",
    })
    db.register("silver_inquiries", df_inq)
    db.execute("CREATE VIEW silver_inquiries AS SELECT * FROM silver_inquiries")

    # gold_experiment_analysis
    db.execute("""
        CREATE VIEW gold_experiment_analysis AS
        SELECT *, 'test_exp' AS experiment_name
        FROM silver_inquiries
    """)

    return db


@pytest.fixture(scope="module")
def app(synthetic_db):
    from continum.ui.app import create_app
    flask_app = create_app(data_dir="./sample_data", debug=False)

    # Inject synthetic DB immediately so routes don't wait for boot
    flask_app.db    = synthetic_db
    flask_app.state = {"mode": "synthetic"}
    flask_app._boot_event.set()   # mark as ready
    flask_app._boot_error = None

    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthRoutes:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.get_json()
        assert "status" in data
        assert "db_ready" in data

    def test_readyz_ready(self, client):
        r = client.get("/readyz")
        assert r.status_code in (200, 503)   # 200 once boot completes


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT ROUTES
# ─────────────────────────────────────────────────────────────────────────────

class TestExperimentRoutes:
    def test_list_experiments(self, client):
        r = client.get("/api/experiments")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)

    def test_select_experiment(self, client):
        r = client.post(
            "/api/experiments/select",
            data=json.dumps({"name": "test_exp"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data.get("ok") is True

    def test_select_experiment_empty_name(self, client):
        r = client.post(
            "/api/experiments/select",
            data=json.dumps({"name": ""}),
            content_type="application/json",
        )
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# MODULE ROUTES
# ─────────────────────────────────────────────────────────────────────────────

class TestModuleRoutes:
    def test_list_modules(self, client):
        r = client.get("/api/modules")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        module_names = [m["name"] for m in data]
        # Core modules must be present
        for expected in ["power_calculator", "experiment_analysis",
                         "causal_analysis", "roi_tracker"]:
            assert expected in module_names, f"{expected} not in module registry"

    def test_module_config_power_calculator(self, client):
        r = client.get("/api/module-config/power_calculator")
        assert r.status_code == 200
        data = r.get_json()
        assert "fields" in data

    def test_module_config_unknown(self, client):
        r = client.get("/api/module-config/nonexistent_module")
        assert r.status_code in (200, 404)   # graceful, not 500


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTION ROUTES
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteRoutes:
    def test_execute_returns_run_id(self, client):
        r = client.post(
            "/api/execute/power_calculator",
            data=json.dumps({
                "params": {
                    "Baseline conversion/IOR rate (0-1)": 0.18,
                    "MDE — minimum detectable effect (% relative, e.g. 10)": 10,
                }
            }),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = r.get_json()
        assert "run_id" in data
        assert len(data["run_id"]) > 0

    def test_execute_db_not_ready(self, app, client):
        original_db = app.db
        app.db = None
        try:
            r = client.post("/api/execute/power_calculator")
            assert r.status_code == 200
            data = r.get_json()
            # Should contain an error key, not raise
            assert "run_id" in data
        finally:
            app.db = original_db

    def test_stream_unknown_run(self, client):
        r = client.get("/api/stream/xxxxxxxx")
        assert r.status_code == 200
        assert b"ERR" in r.data or b"UNKNOWN_RUN" in r.data


# ─────────────────────────────────────────────────────────────────────────────
# SESSION ROUTES
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionRoutes:
    def test_session_select_experiment(self, client):
        r = client.post(
            "/api/session/select-experiment",
            data=json.dumps({"name": "test_exp"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data.get("ok") is True
        assert data.get("active") == "test_exp"

    def test_session_select_no_name(self, client):
        r = client.post(
            "/api/session/select-experiment",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# ATTRIBUTE INTEGRITY  (regression — the continum_* mismatch)
# ─────────────────────────────────────────────────────────────────────────────

class TestAppAttributeIntegrity:
    def test_canonical_db_attr(self, app):
        assert hasattr(app, "db"), "app.db missing"

    def test_canonical_ses_attr(self, app):
        assert hasattr(app, "ses"), "app.ses missing"

    def test_canonical_bus_attr(self, app):
        assert hasattr(app, "bus"), "app.bus missing"

    def test_backcompat_continum_db(self, app):
        assert app.continum_db is app.db, "app.continum_db alias broken"

    def test_backcompat_continum_session(self, app):
        assert app.continum_session is app.ses, "app.continum_session alias broken"

    def test_backcompat_continum_bus(self, app):
        assert app.continum_bus is app.bus, "app.continum_bus alias broken"

    def test_boot_event_exists(self, app):
        assert hasattr(app, "_boot_event"), "app._boot_event missing"

    def test_boot_event_set(self, app):
        assert app._boot_event.is_set(), "Boot event not set after fixture injection"
