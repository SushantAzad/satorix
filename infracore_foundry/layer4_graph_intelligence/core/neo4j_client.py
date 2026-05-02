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
    logger.info("Layer 4 Neo4j driver ready (read-only pool, size=%d)", settings.neo4j_max_pool_size)


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
