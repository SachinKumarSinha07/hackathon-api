"""
Application Configuration Module

All configuration settings for the FastAPI application.
Values are loaded from environment variables / .env file via pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List
from pathlib import Path

# Project root directory - used for resolving relative paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application Settings
    app_name: str = "Hackathon API"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = True

    # Logging Settings
    log_level: str = "INFO"

    # API Settings
    api_prefix: str = "/api/v1"

    # CORS Settings
    allowed_origins: str = "http://localhost:3000"

    # PostgreSQL Settings
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "hackathon"
    # Full override; when set it takes precedence over the individual parts.
    database_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    def get_allowed_origins_list(self) -> List[str]:
        """Convert ALLOWED_ORIGINS string to a list. Supports '*' or comma-separated values."""
        if self.allowed_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    def get_database_url(self) -> str:
        """Build the SQLAlchemy PostgreSQL connection URL."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache()
def get_settings() -> Settings:
    """Create and cache the settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
