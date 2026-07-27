from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Information
    APP_NAME: str = "Continum Retail Experimentation Assistant"
    DEBUG: bool = False

    # LLM & Model Settings
    LLM_MODEL: str = "gpt-4o"
    LLM_TEMPERATURE: float = 0.0

    # Storage & Connectors
    DATABASE_URL: str = "sqlite:///./sample_data/Xometry/xometry.db"
    VECTOR_STORE_PATH: str = "./runtime_data/vector_store"

    # StatSig Integration
    STATSIG_API_KEY: Optional[str] = None
    STATSIG_BASE_URL: str = "https://statsigapi.net/v1"

    # MCP Server Configuration
    MCP_SERVER_HOST: str = "0.0.0.0"
    MCP_SERVER_PORT: int = 8000

    # LangGraph Persistence Checkpointer
    CHECKPOINTER_DB_URL: str = "sqlite:///./runtime_data/checkpointer.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()