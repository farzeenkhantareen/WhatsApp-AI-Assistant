"""Manual send endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.api.schemas import SendMessageRequest, SendMessageResponse
from app.middleware.rate_limit import enforce_rate_limit
from app.services.evolution_client import evolution_client
from app.utils.phone import normalize_phone
from app.utils.sanitize import sanitize_text
from app.utils.security import verify_internal_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["send"], dependencies=[Depends(verify_internal_api_key)])


@router.post("/send", response_model=SendMessageResponse)
async def send_message(body: SendMessageRequest, request: Request) -> SendMessageResponse:
    await enforce_rate_limit(request, bucket="send")
    phone = normalize_phone(body.phone)
    if not phone:
        return SendMessageResponse(success=False, phone="", detail="Invalid phone")

    try:
        if body.media_url:
            media_type = (body.media_type or "image").lower()
            await evolution_client.send_media(
                phone,
                media_url=body.media_url,
                media_type=media_type,
                caption=sanitize_text(body.caption or body.message or ""),
                file_name=body.file_name,
            )
            detail = f"media ({media_type}) sent"
        else:
            text = sanitize_text(body.message)
            if not text:
                return SendMessageResponse(
                    success=False, phone=phone, detail="message is required"
                )
            await evolution_client.send_text(phone, text)
            detail = "text sent"
        return SendMessageResponse(success=True, phone=phone, detail=detail)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Send failed: %s", exc)
        return SendMessageResponse(success=False, phone=phone, detail=str(exc))
