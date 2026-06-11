from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # PostgreSQL (read + limited write-back via Funnel)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "infracore"
    postgres_user: str = "infracore"
    postgres_password: str = "infracore_dev_password"

    # Neo4j — read-only pool for graph queries
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "infracore123"
    neo4j_max_pool_size: int = 10

    # Elasticsearch — read-only
    elasticsearch_url: str = "http://localhost:9200"

    # Redis — read-cache + cache-invalidation consumer
    redis_url: str = "redis://localhost:6379/0"
    redis_ttl_short: int = 3600       # 1h  — volatile results
    redis_ttl_medium: int = 21600     # 6h  — batch results
    redis_ttl_long: int = 86400       # 24h — LLM narratives

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "satorix-l4-cache-invalidator"

    # Layer 3 URL (for Funnel write-back via HTTP fallback)
    layer3_api_url: str = "http://localhost:8003"

    # Anthropic
    anthropic_api_key: Optional[str] = None

    # API
    layer4_api_port: int = 8004
    api_host: str = "0.0.0.0"
    log_level: str = "INFO"
    api_key: Optional[str] = None

    # GDS
    gds_projection_name: str = "satorix-full"
    gds_betweenness_sample_threshold: int = 100_000   # use sampled above this

    # Batch
    batch_betweenness_top_k: int = 500    # store scores for top-k only
    risk_score_batch_size: int = 200

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
