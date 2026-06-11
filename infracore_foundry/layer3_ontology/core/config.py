from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "infracore"
    postgres_user: str = "infracore"
    postgres_password: str = "infracore_dev_password"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "infracore123"

    # Elasticsearch
    elasticsearch_url: str = "http://localhost:9200"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "infracore_minio"
    minio_secret_key: str = "infracore_minio_secret"
    minio_secure: bool = False
    minio_raw_bucket: str = "raw-data"

    # Layer 3 API
    layer3_api_port: int = 8003
    api_host: str = "0.0.0.0"
    log_level: str = "INFO"
    api_key: Optional[str] = None

    # Schema
    schema_version: str = "1.0.0"

    # Performance
    risk_score_batch_size: int = 100
    ingest_chunk_size: int = 1000

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


settings = Settings()
