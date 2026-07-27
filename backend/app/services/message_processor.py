"""Inbound WhatsApp message processing pipeline."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.database.session import AsyncSessionLocal
from app.memory.conversation_memory import ConversationMemory
from app.memory.debounce import debouncer
from app.services.evolution_client import evolution_client
from app.services.media_service import (
    classify_message,
    document_is_pdf,
    ensure_data_uri,
    extract_text_body,
)
from app.services.openrouter_client import openrouter_client
from app.services.pdf_service import extract_pdf_text_from_base64
from app.services.tools import TOOL_DEFINITIONS, build_system_prompt, execute_tool
from app.services.transcription import transcribe_voice
from app.utils.phone import is_group_jid, normalize_phone
from app.utils.sanitize import sanitize_text

logger = logging.getLogger(__name__)


def parse_incoming_webhook(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Normalize an Evolution webhook payload into a processable event dict.

    Returns None when the event should be ignored.
    """
    event = str(payload.get("event") or payload.get("type") or "").lower()
    data = payload.get("data") or payload

    # Connection events are handled separately
    if "connection" in event:
        return {
            "kind": "connection",
            "event": event,
            "data": data,
            "state": _extract_connection_state(data),
        }

    if "qrcode" in event:
        return {"kind": "qrcode", "event": event, "data": data}

    # Messages upsert (and similar)
    if event and "messages" not in event and "message" not in event:
        # Unknown event — ignore quietly
        if event not in {"", "messages.upsert", "messages_upsert"}:
            logger.debug("Ignoring webhook event=%s", event)
            return None

    message_data = data
    if isinstance(data, dict) and "message" in data and "key" in data:
        message_data = data
    elif isinstance(data, list) and data:
        message_data = data[0]
    elif isinstance(data, dict) and "messages" in data:
        msgs = data["messages"]
        message_data = msgs[0] if msgs else data

    if not isinstance(message_data, dict):
        return None

    key = message_data.get("key") or {}
    if key.get("fromMe") is True:
        return None

    remote_jid = key.get("remoteJid") or message_data.get("remoteJid") or ""
    if is_group_jid(remote_jid):
        return None

    phone = normalize_phone(remote_jid)
    if not phone:
        return None

    message = message_data.get("message") or {}
    if not isinstance(message, dict):
        message = {}

    kind, media_node = classify_message(message)
    text = extract_text_body(message)

    return {
        "kind": "message",
        "phone": phone,
        "remote_jid": remote_jid,
        "message_id": key.get("id"),
        "message_kind": kind,
        "text": text,
        "media_node": media_node,
        "raw_message": message,
        "raw_payload": message_data,
    }


def _extract_connection_state(data: Any) -> str:
    if not isinstance(data, dict):
        return "unknown"
    state = data.get("state") or data.get("status")
    if isinstance(state, dict):
        state = state.get("state") or state.get("status")
    instance = data.get("instance")
    if not state and isinstance(instance, dict):
        state = instance.get("state") or instance.get("status")
    return str(state or "unknown").lower()


async def handle_webhook_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for webhook router."""
    parsed = parse_incoming_webhook(payload)
    if not parsed:
        return {"processed": False, "detail": "ignored"}

    if parsed["kind"] == "connection":
        return await handle_connection_event(parsed)

    if parsed["kind"] == "qrcode":
        logger.info("QR code updated for instance")
        return {"processed": True, "detail": "qrcode acknowledged"}

    # Debounce message bursts
    phone = parsed["phone"]
    await debouncer.add(phone, parsed, on_flush=_flush_messages)
    return {"processed": True, "detail": "queued"}


async def handle_connection_event(parsed: Dict[str, Any]) -> Dict[str, Any]:
    state = parsed.get("state") or "unknown"
    logger.warning("Evolution CONNECTION_UPDATE state=%s", state)
    if state in {"close", "closed", "refused", "disconnected"}:
        try:
            await evolution_client.restart()
            await evolution_client.connect()
            logger.info("Attempted Evolution reconnect after state=%s", state)
        except Exception as exc:  # noqa: BLE001
            logger.error("Reconnect attempt failed: %s", exc)
    return {"processed": True, "detail": f"connection state={state}"}


async def _flush_messages(phone: str, items: List[Dict[str, Any]]) -> None:
    async with AsyncSessionLocal() as session:
        try:
            await process_message_batch(session, phone, items)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Failed processing batch for phone=%s", phone)
            raise


async def process_message_batch(
    session: AsyncSession, phone: str, items: List[Dict[str, Any]]
) -> str:
    """Process one or more debounced inbound messages and send a reply."""
    settings = get_settings()
    memory = ConversationMemory(session)

    user_fragments: List[str] = []
    last_item: Dict[str, Any] = items[-1]
    vision_image: Optional[str] = None

    for item in items:
        text, image_uri = await resolve_user_content(item)
        text = sanitize_text(text)
        if text:
            user_fragments.append(text)
            await memory.append_message(
                phone,
                "user",
                text,
                media_type=item.get("message_kind"),
                raw_payload=item.get("raw_payload"),
            )
        if image_uri:
            vision_image = image_uri

        # Read receipt + typing
        if item.get("message_id"):
            await evolution_client.mark_as_read(
                item.get("remote_jid") or phone, item["message_id"]
            )

    combined_user = "\n".join(user_fragments).strip()
    if not combined_user and not vision_image:
        combined_user = "[Empty message]"
        await memory.append_message(phone, "user", combined_user)

    await evolution_client.send_presence(phone, "composing")

    history = await memory.get_history_for_llm(phone)
    # History already contains the new user messages from append; build LLM messages
    llm_messages = _history_to_llm(history)
    # Ensure system prompt is first
    system = build_system_prompt()
    messages_for_model: List[Dict[str, Any]] = [{"role": "system", "content": system}]
    messages_for_model.extend(llm_messages)

    if vision_image:
        # Replace last user turn with multimodal content when an image is present
        prompt = combined_user or "Please analyze this image."
        # Remove trailing user message so we can replace
        while messages_for_model and messages_for_model[-1].get("role") == "user":
            messages_for_model.pop()
        messages_for_model.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": vision_image}},
                ],
            }
        )
        reply = await openrouter_client.complete_text(
            messages_for_model, model=settings.openrouter_vision_model
        )
    else:
        reply = await openrouter_client.complete_with_tools(
            messages_for_model,
            TOOL_DEFINITIONS,
            execute_tool,
            model=settings.openrouter_model,
            temperature=settings.openrouter_temperature,
        )

    reply = sanitize_text(reply) or "Sorry, I could not generate a reply."
    await memory.append_message(phone, "assistant", reply)
    await evolution_client.send_presence(phone, "paused")
    await evolution_client.send_text(phone, reply)
    logger.info("Replied to phone=%s chars=%s", phone, len(reply))
    return reply


async def resolve_user_content(item: Dict[str, Any]) -> tuple[str, Optional[str]]:
    """Return (text, optional image data URI)."""
    kind = item.get("message_kind") or "text"
    text = item.get("text") or ""
    raw_message = item.get("raw_message") or {}
    media_node = item.get("media_node")

    if kind == "text":
        return text, None

    base64_data = await _resolve_media_base64(item)
    if kind == "image" and base64_data:
        mime = (media_node or {}).get("mimetype") or "image/jpeg"
        return text or "Please analyze this image.", ensure_data_uri(base64_data, mime)

    if kind == "audio" and base64_data:
        mime = (media_node or {}).get("mimetype") or "audio/ogg"
        transcript = await transcribe_voice(base64_data, mimetype=mime)
        return f"[Voice message transcription]\n{transcript}", None

    if kind == "document":
        if document_is_pdf(media_node) and base64_data:
            pdf_text = extract_pdf_text_from_base64(base64_data)
            caption = text.strip()
            body = (
                f"[PDF document content]\n{pdf_text}"
                if not caption
                else f"{caption}\n\n[PDF document content]\n{pdf_text}"
            )
            return body, None
        name = (media_node or {}).get("fileName") or "document"
        return text or f"[Received document: {name}]", None

    if kind == "sticker" and base64_data:
        mime = (media_node or {}).get("mimetype") or "image/webp"
        return text or "User sent a sticker.", ensure_data_uri(base64_data, mime)

    return text or f"[Unsupported message type: {kind}]", None


async def _resolve_media_base64(item: Dict[str, Any]) -> Optional[str]:
    raw_payload = item.get("raw_payload") or {}
    # Some Evolution configs already embed base64
    message = item.get("raw_message") or {}
    for key in ("base64", "messageBase64"):
        if isinstance(raw_payload.get(key), str):
            return raw_payload[key]

    try:
        return await evolution_client.get_base64_from_media_message(
            {"key": raw_payload.get("key"), "message": message}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Media base64 resolve failed: %s", exc)
        return None


def _history_to_llm(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in history:
        role = item.get("role") or "user"
        if role not in {"user", "assistant", "system", "tool"}:
            role = "user"
        content = item.get("content") or ""
        # Skip tool rows without tool_call_id when feeding plain completions
        if role == "tool":
            continue
        out.append({"role": role, "content": content})
    return out
