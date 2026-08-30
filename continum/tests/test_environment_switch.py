"""
Guards the local <-> Databricks switch.

The whole integration rests on one rule: the same source runs in both
environments, selected by configuration alone. `get_llm()`/`get_fallback_llm()`
are built lazily on first request (see orchestration/supervisor.py), so a
machine with no workspace credentials can still import and boot; these tests
cover the provider-selection logic itself, called directly with overrides.
"""

import pytest
from continum.config import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        DEPLOY_TARGET="auto",
        GEMINI_API_KEY="",
        OPENAI_API_KEY="",
        LAKEBASE_ENDPOINT="",
        DATABRICKS_WAREHOUSE_ID="",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _no_ambient_databricks(monkeypatch):
    # These are injected by Databricks Apps; a developer machine that happens to
    # have them set must not flip the tests into databricks mode.
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def test_auto_resolves_to_local_without_workspace_env():
    assert _settings().is_databricks is False


def test_auto_resolves_to_databricks_when_host_is_injected(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com")
    assert _settings().is_databricks is True


def test_auto_resolves_to_databricks_when_client_id_is_injected(monkeypatch):
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "some-service-principal")
    assert _settings().is_databricks is True


def test_explicit_local_overrides_injected_workspace_env(monkeypatch):
    # Lets a Databricks job run against local fixtures.
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com")
    assert _settings(DEPLOY_TARGET="local").is_databricks is False


def test_explicit_databricks_overrides_absent_workspace_env():
    # Lets a laptop test against a real workspace.
    assert _settings(DEPLOY_TARGET="databricks").is_databricks is True


def test_gemini_wins_when_both_keys_are_present():
    llm = _settings(GEMINI_API_KEY="g-key", OPENAI_API_KEY="o-key").get_llm()
    assert type(llm).__name__ == "ChatGoogleGenerativeAI"


def test_openai_is_used_when_only_openai_key_is_present():
    llm = _settings(OPENAI_API_KEY="o-key").get_llm()
    assert type(llm).__name__ == "ChatOpenAI"


def test_explicit_keys_win_over_databricks(monkeypatch):
    """
    A developer with workspace credentials in their environment must keep
    exercising the local path, otherwise the local provider stops being tested.
    """
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com")
    llm = _settings(GEMINI_API_KEY="g-key").get_llm()
    assert type(llm).__name__ == "ChatGoogleGenerativeAI"


def test_no_credentials_anywhere_raises_an_actionable_error():
    with pytest.raises(ValueError, match="No valid API key"):
        _settings().get_llm()


def test_fallback_is_offered_only_when_a_second_provider_exists():
    assert _settings(GEMINI_API_KEY="g", OPENAI_API_KEY="o").get_fallback_llm() is not None
    # Gemini alone has nothing to fall back to.
    assert _settings(GEMINI_API_KEY="g").get_fallback_llm() is None
    # OpenAI is already the primary here, so it is not also its own fallback.
    assert _settings(OPENAI_API_KEY="o").get_fallback_llm() is None


@pytest.mark.parametrize("schema", ["app", "app_v1", "_private", "S1"])
def test_safe_schema_accepts_plain_identifiers(schema):
    assert _settings().safe_schema(schema) == schema


@pytest.mark.parametrize(
    "schema", ["bad; DROP TABLE x", "app-v1", "app v1", "", '"quoted"', "1app"]
)
def test_safe_schema_rejects_anything_that_is_not_an_identifier(schema):
    # Schema names cannot be bound as SQL parameters, so they are validated
    # rather than escaped.
    with pytest.raises(ValueError, match="Unsafe SQL schema name"):
        _settings().safe_schema(schema)
