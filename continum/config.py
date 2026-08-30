import os
import re
from typing import Literal, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic_settings import BaseSettings, SettingsConfigDict

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

STATIC_DOMAIN_TABLES = {"accounts", "users", "stores", "customers", "metric_catalog"}
DYNAMIC_EXPERIMENT_TABLES = {
    "experiments",
    "variants",
    "experiment_exposures",
    "experiment_assignments",
    "experiment_results",
    "learnings_archive",
}


class Settings(BaseSettings):
    APP_NAME: str = "Continum Retail Experimentation Engine"
    ENVIRONMENT: str = "development"

    # Which environment this process is running in.
    #   auto       -> databricks when the workspace env vars are injected, else local
    #   local      -> force the local stack (sqlite, Gemini/OpenAI)
    #   databricks -> force the Databricks stack (Lakebase, Unity Catalog, FMAPI)
    # Explicit values let a laptop test against a workspace, and let a Databricks
    # job run on fixtures, without editing code.
    DEPLOY_TARGET: Literal["auto", "local", "databricks"] = "auto"

    # LLM Settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o"
    LLM_TEMPERATURE: float = 0.0

    # Database and Data Paths
    DATABASE_URL: str = "sqlite:///./matchview_omnichannel.db"
    DEFAULT_SQLITE_PATH: str = "matchview_omnichannel.db"
    ECOMM_CSV_DIR: str = "sample_data/Ecommerce"
    STORE_CSV_DIR: str = "sample_data/Store"
    EXPORT_DIR: str = "runtime_data/exports"

    # StatSig Telemetry Connector
    STATSIG_API_KEY: str = ""
    STATSIG_BASE_URL: str = "https://statsigapi.net/v1"

    # Databricks — all optional. Every adapter that needs one of these degrades
    # with an actionable message when it is unset, so local dev never requires
    # a workspace.
    LAKEBASE_ENDPOINT: str = ""
    LAKEBASE_DATABASE: str = "matchview"
    LAKEBASE_SCHEMA: str = "app"
    DATABRICKS_WAREHOUSE_ID: str = ""
    FMAPI_DEFAULT_ENDPOINT: str = "databricks-claude-sonnet-4-6"
    UC_CATALOG: str = "dev"
    UC_SCHEMA: str = "matchview_store"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def is_databricks(self) -> bool:
        """
        Resolved once per call site rather than having each adapter re-sniff env
        vars, so every capability agrees on which environment it is in.
        """
        if self.DEPLOY_TARGET == "databricks":
            return True
        if self.DEPLOY_TARGET == "local":
            return False
        # auto: Databricks Apps injects these into the app's environment.
        return bool(os.getenv("DATABRICKS_HOST") or os.getenv("DATABRICKS_CLIENT_ID"))

    def safe_schema(self, schema: str) -> str:
        """
        Schema names reach SQL by string interpolation (they cannot be bound as
        parameters), so validate them as plain identifiers before use.
        """
        if not _IDENTIFIER.match(schema):
            raise ValueError(f"Unsafe SQL schema name: {schema!r}")
        return schema

    def _build_openai(self) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.LLM_MODEL,
            api_key=self.OPENAI_API_KEY,
            temperature=self.LLM_TEMPERATURE,
        )

    def _build_fmapi(self) -> BaseChatModel:
        """
        Databricks Foundation Model API. FMAPI is OpenAI-wire-compatible, so it is
        reached through ChatOpenAI pointed at the workspace's serving endpoints —
        that keeps tool binding and streaming working through the existing
        LangGraph path with no other change.

        The token is short-lived and minted per call rather than cached, so a
        long-running worker cannot go stale mid-session. Imports are local so a
        machine without databricks-sdk installed can still import this module.
        """
        from databricks.sdk import WorkspaceClient
        from langchain_openai import ChatOpenAI

        workspace = WorkspaceClient()
        headers: dict[str, str] = {}
        workspace.config.authenticate()(headers)
        token = headers.get("Authorization", "").removeprefix("Bearer ")
        if not token:
            raise ValueError(
                "Databricks authentication returned no token. Check the workspace "
                "credentials available to this process."
            )

        return ChatOpenAI(
            model=self.FMAPI_DEFAULT_ENDPOINT,
            api_key=token,
            base_url=f"{workspace.config.host}/serving-endpoints",
            temperature=self.LLM_TEMPERATURE,
            # Kept under typical gateway timeouts so a stalled call surfaces as a
            # handled failure rather than hanging the whole chat request.
            timeout=20.0,
        )

    def get_llm(self) -> BaseChatModel:
        """
        Picks a chat model by which credentials are present. Gemini and OpenAI come
        first so a developer with workspace credentials in their environment does
        not silently stop exercising the local path; FMAPI is used when running on
        Databricks with no explicit key configured.
        """
        gemini_key = self.GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY", "")

        if gemini_key:
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=self.GEMINI_MODEL,
                google_api_key=gemini_key,
                temperature=self.LLM_TEMPERATURE,
            )
        elif self.OPENAI_API_KEY:
            return self._build_openai()
        elif self.is_databricks:
            return self._build_fmapi()
        else:
            raise ValueError(
                "No valid API key found. Please set GEMINI_API_KEY (or GOOGLE_API_KEY) "
                "or OPENAI_API_KEY in your .env file."
            )

    def get_fallback_llm(self) -> Optional[BaseChatModel]:
        """
        A second provider to retry with when the primary provider's call fails at
        REQUEST time (auth, quota, network, IP restrictions) rather than at
        startup. `get_llm()` picks a provider once, at import, based only on
        whether a key is present — it never verifies the key actually works, so a
        request-time failure there is otherwise unrecoverable for the rest of the
        process's life.

        Only Gemini -> OpenAI is offered: Gemini is the only provider `get_llm()`
        can prefer over another one that is also configured, so it's the only
        case where a second, already-configured provider exists to fall back to.
        """
        gemini_key = self.GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY", "")
        if gemini_key and self.OPENAI_API_KEY:
            return self._build_openai()
        return None


settings = Settings()
