"""
Layer 6 Redis client — async connection, cache helpers.
"""
import json
import logging
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Return (and lazily create) the shared async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection on application shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed.")


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

async def cache_response(key: str, data: Any, ttl: int = 300) -> None:
    """
    Serialise *data* to JSON and store it in Redis under *key* with a TTL of
    *ttl* seconds (default 5 minutes).
    """
    try:
        client = await get_redis()
        await client.setex(key, ttl, json.dumps(data, default=str))
    except Exception as exc:
        logger.warning("cache_response failed for key '%s': %s", key, exc)


async def get_cached(key: str) -> Optional[Dict]:
    """
    Return the cached value for *key*, or None if absent / on error.
    """
    try:
        client = await get_redis()
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("get_cached failed for key '%s': %s", key, exc)
        return None


async def invalidate(key: str) -> None:
    """Delete a single cache key."""
    try:
        client = await get_redis()
        await client.delete(key)
    except Exception as exc:
        logger.warning("invalidate failed for key '%s': %s", key, exc)


async def invalidate_pattern(pattern: str) -> None:
    """
    Delete all keys matching *pattern* (e.g. ``"entity:company:*"``).

    Uses SCAN to avoid blocking the Redis server.
    """
    try:
        client = await get_redis()
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = await client.scan(cursor, match=pattern, count=100)
            if keys:
                await client.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        logger.debug("invalidate_pattern '%s' — deleted %d keys.", pattern, deleted)
    except Exception as exc:
        logger.warning("invalidate_pattern failed for pattern '%s': %s", pattern, exc)
