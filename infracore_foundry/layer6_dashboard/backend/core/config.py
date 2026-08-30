"""
Layer 6 configuration — all values pulled from environment variables with sensible defaults.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # JWT
    jwt_secret_key: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # Database
    postgres_url: str = (
        "postgresql+asyncpg://infracore:infracore_dev_password@postgres:5432/infracore"
    )

    # Redis
    redis_url: str = "redis://redis:6379/1"

    # Upstream layer URLs
    api_key: str = ""
    layer1_api_url: str = "http://layer1-api:8001"
    layer2_api_url: str = "http://layer2-api:8002"
    layer3_api_url: str = "http://layer3-api:8003"
    layer4_api_url: str = "http://layer4-api:8004"
    layer5_api_url: str = "http://layer5-api:8005"

    # Kafka
    kafka_bootstrap_servers: str = "kafka:9092"

    # Layer 6 ports
    layer6_api_port: int = 8006
    layer6_ws_port: int = 8007

    # Default admin credentials (change in production)
    default_admin_email: str = "admin@satorix.internal"
    default_admin_password: str = "SatorixAdmin2026!"
    default_admin_client_id: str = "PLATFORM_GLOBAL"

    # CORS
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
