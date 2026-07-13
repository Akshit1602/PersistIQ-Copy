"""Routing assertion for the AskData visualization path (langgraph-routing skill).

A data/chart question that trips a KIND_DATA tool trigger (e.g. "... rate by ...",
"conversion by ...") must flow straight through AskData — which produces the
chart — instead of being intercepted with a "run <tool>?" confirmation. A
KIND_DEPLOY/KIND_ANALYSIS intent must still confirm. These are deterministic:
`_answer_data` is patched so no live LLM is needed.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture(scope="module")
def client():
    import duckdb
    import numpy as np
    import pandas as pd

    from continum.userui.app import create_app

    db = duckdb.connect(":memory:")
    rng = np.random.default_rng(7)
    n = 500
    df = pd.DataFrame(
        {
            "variant": rng.choice(["control", "treatment"], n),
            "converted_to_order": rng.choice([0, 1], n, p=[0.82, 0.18]),
            "order_value": rng.uniform(1000, 8000, n),
            "account_segment": rng.choice(["Core", "Growth"], n),
            "experiment_name": "test_exp",
        }
    )
    db.register("silver_inquiries", df)
    db.execute("CREATE VIEW silver_inquiries AS SELECT * FROM silver_inquiries")
    db.execute(
        "CREATE VIEW gold_experiment_analysis AS SELECT *, 'test_exp' AS ename FROM silver_inquiries"
    )

    app = create_app(data_dir="./sample_data", debug=False)
    app.db = db
    app.state = {"mode": "synthetic"}
    app._boot_event.set()
    app._boot_error = None
    if getattr(app, "ses", None) is not None:
        app.ses.active_dataset = "experiments"  # pass the dataset gate
    app.config["TESTING"] = True
    return app.test_client()


def _ask(client, question):
    r = client.post(
        "/api/copilot/ask",
        data=json.dumps({"question": question, "mode": "auto"}),
        content_type="application/json",
    )
    return r.get_json()


_FAKE_DATA = {
    "response": "Here is the breakdown.",
    "sql": "SELECT variant, AVG(converted_to_order) FROM silver_inquiries GROUP BY variant",
    "table": [{"variant": "control", "rate": 0.18}, {"variant": "treatment", "rate": 0.20}],
    "columns": ["variant", "rate"],
    "visualizations": [{"type": "bar", "x": "variant", "y": "rate", "title": "Rate by variant"}],
    "provider": "azure",
}


@pytest.mark.parametrize(
    "q",
    [
        "plot conversion rate by variant",
        "chart conversion by variant",
        "show me the breakdown by account segment",
    ],
)
def test_data_chart_query_flows_through_askdata_not_confirm(client, q):
    """A KIND_DATA tool trigger must NOT be gated behind a confirmation prompt;
    it routes through AskData and surfaces the visualization."""
    with patch("continum.userui.routes.api._answer_data", return_value=_FAKE_DATA):
        d = _ask(client, q)
    assert d["mode"] != "confirm", f"{q!r} was intercepted with a tool confirmation"
    assert d.get("pending_tool") is None
    assert d.get("visualizations"), f"{q!r} should surface a visualization payload"


def test_deploy_intent_still_confirms(client):
    """Guardrail preserved: a go-live intent still asks for confirmation."""
    d = _ask(client, "launch this campaign now")
    assert d.get("mode") == "confirm"
    assert (d.get("pending_tool") or {}).get("kind") == "deploy"
