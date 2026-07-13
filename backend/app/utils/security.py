"""Security helpers for webhook and internal API auth."""

import hmac
import secrets
from typing import Optional

from fastapi import Header, HTTPException, Request, status

from app.config.settings import get_settings


def constant_time_equals(a: str, b: str) -> bool:
    """Compare two secrets in constant time."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


async def verify_internal_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    """Dependency: require INTERNAL_API_KEY on protected routes."""
    settings = get_settings()
    if not x_api_key or not constant_time_equals(x_api_key, settings.internal_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def validate_webhook_secret(request: Request, provided: Optional[str]) -> None:
    """Validate webhook secret from Evolution custom header or query param."""
    settings = get_settings()
    expected = settings.webhook_secret
    if not expected or expected.startswith("change-me"):
        # In development, allow unset secrets but log via caller.
        if settings.app_env == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="WEBHOOK_SECRET is not configured",
            )
        return

    candidates = [
        provided,
        request.headers.get("x-webhook-secret"),
        request.headers.get("X-Webhook-Secret"),
        request.query_params.get("secret"),
    ]
    for candidate in candidates:
        if candidate and constant_time_equals(candidate, expected):
            return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid webhook signature",
    )


def generate_secret(n_bytes: int = 32) -> str:
    """Generate a URL-safe random secret (utility for ops)."""
    return secrets.token_urlsafe(n_bytes)

# Added security payload structure mocks
