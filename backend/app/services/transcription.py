"""Voice transcription via OpenRouter multimodal models."""

from __future__ import annotations

import logging
from typing import Optional

from app.services.media_service import ensure_data_uri
from app.services.openrouter_client import openrouter_client

logger = logging.getLogger(__name__)


async def transcribe_voice(
    base64_audio: str,
    *,
    mimetype: str = "audio/ogg",
) -> str:
    """Transcribe a WhatsApp voice note from base64 payload."""
    data_uri = ensure_data_uri(base64_audio, mimetype)
    text = await openrouter_client.transcribe_audio_data_uri(data_uri)
    cleaned = (text or "").strip()
    if not cleaned:
        return "[Empty transcription]"
    logger.info("Transcribed voice note length=%s", len(cleaned))
    return cleaned
