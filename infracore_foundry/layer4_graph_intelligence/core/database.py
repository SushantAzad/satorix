import asyncpg
import logging
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_db_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
            f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}",
        min_size=2,
        max_size=10,
    )
    async with _pool.acquire() as conn:
        with open("/app/migrations/l4_schema.sql") as f:
            await conn.execute(f.read())
    logger.info("Layer 4 DB pool ready, schema applied")


async def close_db_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_db_pool() first")
    return _pool
