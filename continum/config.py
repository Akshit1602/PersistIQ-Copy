import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from langchain_core.language_models.chat_models import BaseChatModel


class Settings(BaseSettings):
    APP_NAME: str = "Continum Retail Experimentation Engine"
    ENVIRONMENT: str = "development"

    # LLM Settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o"
    LLM_TEMPERATURE: float = 0.0

    # Database
    DATABASE_URL: str = "sqlite:///./continum_warehouse.db"

    # StatSig Telemetry Connector
    STATSIG_API_KEY: str = ""
    STATSIG_BASE_URL: str = "https://statsigapi.net/v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_llm(self) -> BaseChatModel:
        """
        Dynamically returns Google Gemini LLM if GEMINI_API_KEY (or GOOGLE_API_KEY)
        is set in .env, otherwise falls back to OpenAI GPT-4o.
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
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.LLM_MODEL,
                api_key=self.OPENAI_API_KEY,
                temperature=self.LLM_TEMPERATURE,
            )
        else:
            raise ValueError(
                "No valid API key found. Please set GEMINI_API_KEY (or GOOGLE_API_KEY) "
                "or OPENAI_API_KEY in your .env file."
            )


settings = Settings()