from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "infracore"
    postgres_user: str = "infracore"
    postgres_password: str = "infracore_dev_password"

    # Neo4j — read-only
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "infracore123"
    neo4j_max_pool_size: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_ttl_short: int = 3600
    redis_ttl_medium: int = 21600
    redis_ttl_long: int = 86400

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "satorix-l5-analytics"

    # MinIO — read processed Parquet from L2
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "infracore_minio"
    minio_secret_key: str = "infracore_minio_secret"
    minio_secure: bool = False
    minio_processed_bucket: str = "processed-data"

    # Upstream API URLs
    layer3_api_url: str = "http://localhost:8003"
    layer4_api_url: str = "http://localhost:8004"

    # Anthropic
    anthropic_api_key: Optional[str] = None

    # Model artifact storage path (MinIO bucket or local)
    model_artifact_bucket: str = "model-artifacts"
    model_artifact_path_prefix: str = "l5_models"

    # Feature store
    feature_schema_version: str = "v1.0"

    # API
    layer5_api_port: int = 8005
    api_host: str = "0.0.0.0"
    log_level: str = "INFO"
    api_key: Optional[str] = None

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_async(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
