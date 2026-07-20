"""Redis-backed rate limiting helpers."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.config.settings import get_settings
from app.database.redis_client import incr_with_expire


async def enforce_rate_limit(request: Request, *, bucket: str | None = None) -> None:
    """Raise 429 when the client exceeds RATE_LIMIT_PER_MINUTE."""
    settings = get_settings()
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return

    client = request.client.host if request.client else "unknown"
    key = f"rate:{bucket or 'ip'}:{client}"
    count = await incr_with_expire(key, 60)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )


async def enforce_phone_rate_limit(phone: str) -> None:
    settings = get_settings()
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return
    key = f"rate:webhook:{phone}"
    count = await incr_with_expire(key, 60)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Webhook rate limit exceeded for phone",
        )
