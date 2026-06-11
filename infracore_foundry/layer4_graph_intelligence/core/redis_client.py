import hashlib
import json
import logging
from typing import Any, Optional
import redis.asyncio as aioredis

from .config import settings

logger = logging.getLogger(__name__)

_client: Optional[aioredis.Redis] = None


async def init_redis() -> None:
    global _client
    _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    await _client.ping()
    logger.info("Layer 4 Redis client ready")


async def close_redis() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None


def get_redis() -> aioredis.Redis:
    if _client is None:
        raise RuntimeError("Redis not initialised — call init_redis() first")
    return _client


def cache_key(subsystem: str, **params) -> str:
    """Deterministic cache key: l4:{subsystem}:{sha256(sorted_params)[:16]}"""
    payload = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"l4:{subsystem}:{digest}"


async def cache_get(key: str) -> Optional[Any]:
    r = get_redis()
    raw = await r.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_set(key: str, value: Any, ttl: int) -> None:
    r = get_redis()
    await r.setex(key, ttl, json.dumps(value, default=str))


async def cache_delete_pattern(pattern: str) -> int:
    r = get_redis()
    keys = await r.keys(pattern)
    if keys:
        return await r.delete(*keys)
    return 0
