"""Debounce buffer for rapid WhatsApp message bursts."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.config.settings import get_settings
from app.database.redis_client import get_redis
from app.utils.phone import normalize_phone

logger = logging.getLogger(__name__)


class MessageDebouncer:
    """Accumulate inbound messages per phone, then flush once after quiet period."""

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    def _buffer_key(self, phone: str) -> str:
        return f"debounce:{normalize_phone(phone)}"

    async def add(
        self,
        phone: str,
        item: Dict[str, Any],
        on_flush: Callable[[str, List[Dict[str, Any]]], Awaitable[None]],
    ) -> None:
        settings = get_settings()
        redis = await get_redis()
        key = self._buffer_key(phone)
        await redis.rpush(key, json.dumps(item, default=str))
        await redis.expire(key, int(settings.message_debounce_seconds) + 30)

        async with self._lock:
            existing = self._tasks.get(phone)
            if existing and not existing.done():
                existing.cancel()
            self._tasks[phone] = asyncio.create_task(
                self._wait_and_flush(phone, on_flush, settings.message_debounce_seconds)
            )

    async def _wait_and_flush(
        self,
        phone: str,
        on_flush: Callable[[str, List[Dict[str, Any]]], Awaitable[None]],
        delay: float,
    ) -> None:
        try:
            await asyncio.sleep(delay)
            items = await self._drain(phone)
            if items:
                await on_flush(phone, items)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Debounce flush failed for phone=%s", phone)

    async def _drain(self, phone: str) -> List[Dict[str, Any]]:
        redis = await get_redis()
        key = self._buffer_key(phone)
        items: List[Dict[str, Any]] = []
        while True:
            raw = await redis.lpop(key)
            if raw is None:
                break
            try:
                items.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("Invalid debounce payload discarded")
        return items


# Process-wide debouncer
debouncer = MessageDebouncer()
