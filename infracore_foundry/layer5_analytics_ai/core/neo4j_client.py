"""Read-only Neo4j client for Layer 5 — mirrors L4 interface."""
import logging
from typing import Optional
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession

from .config import settings

logger = logging.getLogger(__name__)

_driver: Optional[AsyncDriver] = None


async def init_neo4j() -> None:
    global _driver
    _driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        max_connection_pool_size=settings.neo4j_max_pool_size,
    )
    await _driver.verify_connectivity()
    logger.info("Layer 5 Neo4j read-only driver ready")


async def close_neo4j() -> None:
    global _driver
    if _driver:
        await _driver.close()
        _driver = None


def get_driver() -> AsyncDriver:
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialised — call init_neo4j() first")
    return _driver


def get_session() -> AsyncSession:
    return get_driver().session(database="neo4j")


class _Neo4jClient:
    async def run_query(self, query: str, parameters: dict | None = None) -> list[dict]:
        async with get_session() as s:
            result = await s.run(query, parameters or {})
            return [dict(r) async for r in result]


neo4j_client = _Neo4jClient()
