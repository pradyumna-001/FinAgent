from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )
    CORS_ALLOW_ORIGINS: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed CORS origins (JSON array in env)",
    )

    DATABASE_URL: str = Field(..., description="Async DSN, e.g. postgresql+asyncpg://")
    MIGRATION_DATABASE_URL: str = Field(..., description="Sync DSN for Alembic, e.g. postgresql+psycopg://")
    REDIS_URL: str = Field(..., description="Redis URL for Celery and SSE")
    SECRET_KEY: str = Field(..., description="FastAPI secret key")
    NVIDIA_API_KEY: str = Field(..., description="NVIDIA API key")
    TAVILY_API_KEY: str = Field(..., description="Tavily API key")
    NVIDIA_BASE_URL: str = Field(default="https://integrate.api.nvidia.com/v1", description="NVIDIA base URL")
    NVIDIA_MODEL: str = Field(default="openai/gpt-oss-20b", description="Primary NVIDIA model")
    NVIDIA_FALLBACK_MODEL: str = Field(default="openai/gpt-oss-20b", description="Fallback model")
    NVIDIA_NEMOTRON_MODEL: str = Field(default="nvidia/nemotron-3-ultra", description="Nemotron 3 Ultra model for editor agent")
    LANGCHAIN_API_KEY: str | None = Field(default=None, description="LangSmith API key")
    LANGCHAIN_TRACING_V2: str = Field(default="false", description="Enable LangSmith tracing")
    TELEGRAM_BOT_TOKEN: str | None = Field(default=None, description="Telegram bot token; absent in dev/CI")
    TELEGRAM_CHAT_ID: int | None = Field(default=None, description="Gestor chat ID for note delivery")
    TELEGRAM_POLL_TIMEOUT_S: int = Field(default=30, description="Long-polling timeout per getUpdates call")
    APPROVAL_TIMEOUT_S: int = Field(default=1800, description="Time budget to await a gestor decision")

settings = Settings()