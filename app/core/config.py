"""
Application Configuration Module

All configuration settings for the FastAPI application.
Values are loaded from environment variables / .env file via pydantic-settings.
"""

from pydantic import Field, AliasChoices
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

    # AWS Bedrock Settings (values come from AWS_REGION / BEDROCK_MODEL_ID env vars)
    aws_region: str = ""
    bedrock_model_id: str = ""
    bedrock_max_tokens: int = 2048
    # Ceiling for the executive summary (~2200 chars). Enforced again in the prompt.
    bedrock_summary_max_tokens: int = 1000
    # Applied only to models that support it (e.g. Sonnet 4.5). Sonnet 5 rejects it
    # and it is skipped automatically based on the model id.
    bedrock_temperature: float | None = 0.2
    bedrock_timeout_seconds: int = 120
    # SECURITY: disables TLS certificate verification on the Bedrock client.
    # Only for local dev behind a corporate TLS-intercepting proxy (e.g. Zscaler).
    # NEVER set this to true outside a local machine - it allows MITM on all
    # Bedrock traffic. Defaults to verified (safe) unless explicitly overridden.
    bedrock_verify_ssl: bool = True

    # AWS auth. Preferred: a Bedrock API key (bearer token). Otherwise boto3 uses
    # its default provider chain (AWS_PROFILE, IAM role, real env vars).
    aws_profile: str = ""
    # Bedrock API key (bearer token). Accepts AWS_BEARER_TOKEN_BEDROCK or BEDROCK_API_KEY.
    bedrock_api_key: str = Field(
        "",
        validation_alias=AliasChoices("AWS_BEARER_TOKEN_BEDROCK", "BEDROCK_API_KEY"),
    )

    # PostgreSQL Settings
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "hackathon"
    # Full override; when set it takes precedence over the individual parts.
    database_url: str | None = None

    # S3 Settings
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "us-east-1"
    s3_bucket_name: str | None = None
    s3_vapt_folder: str = "vapt-reports"
    # Expiry (in seconds) for presigned POC image URLs. Default: 7 days (max for SigV4).
    s3_presigned_url_expiry: int = 604800

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
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
