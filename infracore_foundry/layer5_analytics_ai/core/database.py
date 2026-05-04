import asyncpg
import logging
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_db_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.postgres_dsn,
        min_size=2,
        max_size=15,
    )
    async with _pool.acquire() as conn:
        import os
        schema_path = os.path.join(os.path.dirname(__file__), "..", "migrations", "l5_schema.sql")
        with open(schema_path) as f:
            await conn.execute(f.read())
    logger.info("Layer 5 DB pool ready, schema applied")


async def close_db_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_db_pool() first")
    return _pool
