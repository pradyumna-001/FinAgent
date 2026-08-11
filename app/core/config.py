from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

    DATABASE_URL: str = Field(..., description="Async DSN, e.g. postgresql+asyncpg://")
    MIGRATION_DATABASE_URL: str = Field(..., description="Sync DSN for Alembic, e.g. postgresql+psycopg://")
    NVIDIA_API_KEY: str = Field(..., description="NVIDIA API key")
    TAVILY_API_KEY: str = Field(..., description="Tavily API key")
    NVIDIA_BASE_URL: str = Field(..., description="NVIDIA base URL")
    NVIDIA_MODEL: str = Field(..., description="Primary NVIDIA model")
    NVIDIA_FALLBACK_MODEL: str = Field(..., description="Fallback model")
    
settings = Settings()