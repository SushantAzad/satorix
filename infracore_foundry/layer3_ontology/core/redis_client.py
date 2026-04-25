import redis.asyncio as aioredis
import json
from typing import Any, Optional
import logging
from .config import settings

logger = logging.getLogger(__name__)

OBJECT_CACHE_TTL = 300      # 5 minutes
QUERY_CACHE_TTL = 60        # 1 minute


class RedisClient:
    def __init__(self) -> None:
        self._client: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        self._client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        await self._client.ping()
        logger.info("Redis connected at %s", settings.redis_url)

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            logger.info("Redis connection closed")

    @property
    def client(self) -> aioredis.Redis:
        if not self._client:
            raise RuntimeError("Redis client not initialized")
        return self._client

    def _object_key(self, object_type: str, primary_key: str) -> str:
        return f"obj:{object_type.lower()}:{primary_key}"

    def _query_key(self, query_hash: str) -> str:
        return f"query:{query_hash}"

    async def get_object(self, object_type: str, primary_key: str) -> Optional[dict[str, Any]]:
        key = self._object_key(object_type, primary_key)
        data = await self.client.get(key)
        if data:
            return json.loads(data)
        return None

    async def set_object(
        self, object_type: str, primary_key: str, data: dict[str, Any], ttl: int = OBJECT_CACHE_TTL
    ) -> None:
        key = self._object_key(object_type, primary_key)
        await self.client.setex(key, ttl, json.dumps(data, default=str))

    async def invalidate_object(self, object_type: str, primary_key: str) -> None:
        key = self._object_key(object_type, primary_key)
        await self.client.delete(key)

    async def get_query_result(self, query_hash: str) -> Optional[Any]:
        key = self._query_key(query_hash)
        data = await self.client.get(key)
        if data:
            return json.loads(data)
        return None

    async def set_query_result(self, query_hash: str, result: Any, ttl: int = QUERY_CACHE_TTL) -> None:
        key = self._query_key(query_hash)
        await self.client.setex(key, ttl, json.dumps(result, default=str))

    async def invalidate_pattern(self, pattern: str) -> None:
        keys = await self.client.keys(pattern)
        if keys:
            await self.client.delete(*keys)


redis_client = RedisClient()
