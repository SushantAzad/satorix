from typing import Any, Optional
import logging
from core.redis_client import redis_client

logger = logging.getLogger(__name__)


class CacheStore:
    async def get(self, object_type: str, primary_key: str) -> Optional[dict[str, Any]]:
        try:
            return await redis_client.get_object(object_type, primary_key)
        except Exception as e:
            logger.warning("Cache get failed: %s", e)
            return None

    async def set(self, object_type: str, primary_key: str, data: dict[str, Any]) -> None:
        try:
            await redis_client.set_object(object_type, primary_key, data)
        except Exception as e:
            logger.warning("Cache set failed: %s", e)

    async def invalidate(self, object_type: str, primary_key: str) -> None:
        try:
            await redis_client.invalidate_object(object_type, primary_key)
        except Exception as e:
            logger.warning("Cache invalidate failed: %s", e)

    async def get_query(self, query_hash: str) -> Optional[Any]:
        try:
            return await redis_client.get_query_result(query_hash)
        except Exception:
            return None

    async def set_query(self, query_hash: str, result: Any) -> None:
        try:
            await redis_client.set_query_result(query_hash, result)
        except Exception as e:
            logger.warning("Cache set_query failed: %s", e)
