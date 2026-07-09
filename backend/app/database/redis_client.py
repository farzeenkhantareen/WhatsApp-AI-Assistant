"""Redis client and helper operations."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

_redis: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Return a shared async Redis client."""
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    """Close the shared Redis client."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def redis_ping() -> bool:
    """Return True if Redis responds to PING."""
    try:
        client = await get_redis()
        return bool(await client.ping())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis ping failed: %s", exc)
        return False


async def cache_get_json(key: str) -> Optional[Any]:
    client = await get_redis()
    raw = await client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_set_json(key: str, value: Any, ttl: Optional[int] = None) -> None:
    client = await get_redis()
    settings = get_settings()
    await client.set(key, json.dumps(value, default=str), ex=ttl or settings.redis_memory_ttl)


async def cache_delete(key: str) -> bool:
    client = await get_redis()
    return bool(await client.delete(key))


async def incr_with_expire(key: str, ttl_seconds: int) -> int:
    """Increment a counter and set expiry on first write."""
    client = await get_redis()
    count = await client.incr(key)
    if count == 1:
        await client.expire(key, ttl_seconds)
    return int(count)

# Optimized key namespaces
