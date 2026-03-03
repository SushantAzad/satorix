"""
Application configuration using pydantic-settings.
Loads all environment variables from .env file.
"""

import logging
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="infracore", alias="POSTGRES_DB")
    postgres_user: str = Field(default="infracore", alias="POSTGRES_USER")
    postgres_password: str = Field(default="infracore_dev_password", alias="POSTGRES_PASSWORD")

    # MinIO
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="infracore_minio", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="infracore_minio_secret", alias="MINIO_SECRET_KEY")
    minio_raw_bucket: str = Field(default="raw-data", alias="MINIO_RAW_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Encryption
    encryption_key: str = Field(default="", alias="ENCRYPTION_KEY")

    # External APIs
    sandbox_api_key: str = Field(default="", alias="SANDBOX_API_KEY")
    google_credentials_path: str = Field(
        default="./credentials/google_service_account.json",
        alias="GOOGLE_CREDENTIALS_PATH",
    )

    # API Server
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8001, alias="API_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore",
    }

    @property
    def database_url(self) -> str:
        """Construct SQLAlchemy database URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """Construct async SQLAlchemy database URL."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.
    Uses lru_cache so settings are only loaded once from env.
    """
    settings = Settings()
    logger.info(
        "Settings loaded",
        extra={
            "postgres_host": settings.postgres_host,
            "minio_endpoint": settings.minio_endpoint,
            "log_level": settings.log_level,
        },
    )
    return settings


CONNECTOR_TYPES: dict[str, Any] = {}


def register_connector(name: str, connector_class: Any) -> None:
    """Register a connector class by name for dynamic lookup."""
    CONNECTOR_TYPES[name] = connector_class
    logger.debug("Registered connector type: %s -> %s", name, connector_class.__name__)


def get_connector_class(name: str) -> Any:
    """Look up a connector class by its registered name."""
    if name not in CONNECTOR_TYPES:
        available = ", ".join(CONNECTOR_TYPES.keys())
        raise ValueError(
            f"Unknown connector type '{name}'. Available types: {available}"
        )
    return CONNECTOR_TYPES[name]
