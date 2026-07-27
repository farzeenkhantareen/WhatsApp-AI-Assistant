"""Webhook router."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Request

from app.api.schemas import WebhookAck
from app.middleware.rate_limit import enforce_rate_limit
from app.services.message_processor import handle_webhook_payload
from app.utils.security import validate_webhook_secret

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


@router.post("/webhook", response_model=WebhookAck)
async def webhook(request: Request) -> WebhookAck:
    """Receive Evolution API webhook events."""
    await enforce_rate_limit(request, bucket="webhook")
    validate_webhook_secret(request, request.headers.get("x-webhook-secret"))

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:  # noqa: BLE001
        logger.warning("Invalid webhook JSON body")
        return WebhookAck(received=True, processed=False, detail="invalid json")

    if not isinstance(payload, dict):
        return WebhookAck(received=True, processed=False, detail="invalid payload")

    try:
        result = await handle_webhook_payload(payload)
        return WebhookAck(
            received=True,
            processed=bool(result.get("processed")),
            detail=str(result.get("detail") or "ok"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Webhook processing error: %s", exc)
        # Return 200 so Evolution does not storm retries for app bugs;
        # connection issues are retried separately.
        return WebhookAck(received=True, processed=False, detail="processing error")

# Webhook verification ensures payloads originate from evolution api
