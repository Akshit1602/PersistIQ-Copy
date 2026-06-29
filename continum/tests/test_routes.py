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
    from continum.userui.app import create_app
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
# ATTRIBUTE INTEGRITY  (regression — the continum_* mismatch)
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# COPILOT — tool detection (unit) + /api/copilot/ask endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestCopilotToolDetection:
    """Deterministic intent detection in continum.orchestrator (no LLM)."""

    def test_audience_intent(self):
        from continum.orchestrator import detect_tool
        assert detect_tool("who should I target?").key == "audience"

    def test_deploy_intent(self):
        from continum.orchestrator import detect_tool, KIND_DEPLOY
        t = detect_tool("launch this campaign now")
        assert t.key == "deploy" and t.kind == KIND_DEPLOY

    def test_howto_is_not_intercepted(self):
        # "How do I…" is a Guide question, not an action.
        from continum.orchestrator import detect_tool
        assert detect_tool("how do I launch a sequence?") is None

    def test_plain_data_question_not_intercepted(self):
        from continum.orchestrator import detect_tool
        assert detect_tool("how many orders are there") is None

    def test_deploy_warning_mentions_live(self):
        from continum.orchestrator import deploy_warning, get_tool
        assert "LIVE" in deploy_warning(get_tool("deploy"))


class TestCopilotRoutes:
    def _ask(self, client, **body):
        return client.post("/api/copilot/ask",
                           data=json.dumps(body), content_type="application/json")

    def test_response_forwards_visualizations_key(self, client):
        # Regression: the endpoint used to drop `visualizations`, so charts never
        # reached the frontend. It must always be present in the response.
        r = self._ask(client, question="who should I target?", mode="auto")
        assert r.status_code == 200
        assert "visualizations" in r.get_json()

    def test_module_intent_asks_for_confirmation(self, client):
        r = self._ask(client, question="who should I target?", mode="auto")
        data = r.get_json()
        assert data.get("pending_tool") is not None
        assert data["pending_tool"]["key"] == "audience"
        assert "Lead Lists" in data["response"]

    def test_deploy_intent_includes_warning(self, client):
        r = self._ask(client, question="launch this campaign now", mode="auto")
        data = r.get_json()
        assert (data.get("pending_tool") or {}).get("kind") == "deploy"
        assert data.get("deploy_warning") and "LIVE" in data["deploy_warning"]

    def test_empty_question_returns_400(self, client):
        r = self._ask(client, question="", mode="auto")
        assert r.status_code == 400


class TestCopilotFlow:
    """Guided experimentation flow (MVP2) — /api/copilot/flow state machine."""

    def _flow(self, client, **body):
        return client.post("/api/copilot/flow",
                           data=json.dumps(body), content_type="application/json")

    def test_start_returns_choosing_with_chips(self, client):
        r = self._flow(client, message="where am I?")
        assert r.status_code == 200
        d = r.get_json()
        assert d["stage"] == "choosing"
        assert isinstance(d["chips"], list) and len(d["chips"]) > 0
        assert "Guided" in d["response"]

    def test_pick_module_enters_filling(self, client):
        d = self._flow(client, message="start", flow_state=None).get_json()
        d = self._flow(client, message="power_calculator",
                       flow_state=d["flow_state"]).get_json()
        assert d["stage"] == "filling"
        assert d["module_key"] == "power_calculator"
        assert d["chips"]  # at least a "use default" chip

    def test_unrecognised_pick_stays_choosing(self, client):
        start = self._flow(client, message="start").get_json()
        d = self._flow(client, message="zzz nonsense qqq",
                       flow_state=start["flow_state"]).get_json()
        assert d["stage"] == "choosing"

    def test_fill_to_confirm_and_run(self, client):
        # Enter filling on power_calculator, then accept defaults to the end.
        d = self._flow(client, message="start").get_json()
        d = self._flow(client, message="power_calculator",
                       flow_state=d["flow_state"]).get_json()
        guard = 0
        while d["stage"] == "filling" and guard < 25:
            d = self._flow(client, message="ok", flow_state=d["flow_state"]).get_json()
            guard += 1
        assert d["stage"] == "confirm"
        assert any("Run" in c["label"] for c in d["chips"])

        # Confirm → hand off to execution.
        d = self._flow(client, message="run", flow_state=d["flow_state"]).get_json()
        assert d["action"] == "run_module"
        assert d["module_key"] == "power_calculator"
        assert isinstance(d["fields"], dict) and len(d["fields"]) > 0

    def test_numeric_validation_reprompts(self, client):
        d = self._flow(client, message="start").get_json()
        d = self._flow(client, message="power_calculator",
                       flow_state=d["flow_state"]).get_json()
        bad = self._flow(client, message="not-a-number",
                         flow_state=d["flow_state"]).get_json()
        # Still on the same step, with a warning prefix.
        assert bad["stage"] == "filling"
        assert "⚠️" in bad["response"]

    def test_no_field_module_goes_straight_to_confirm(self, client):
        d = self._flow(client, message="start").get_json()
        d = self._flow(client, message="schema_discovery",
                       flow_state=d["flow_state"]).get_json()
        assert d["stage"] == "confirm"

    def test_cancel_returns_to_choosing(self, client):
        d = self._flow(client, message="start").get_json()
        d = self._flow(client, message="schema_discovery",
                       flow_state=d["flow_state"]).get_json()
        d = self._flow(client, message="__cancel__",
                       flow_state=d["flow_state"]).get_json()
        assert d["stage"] == "choosing"


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
