"""Media helpers: build data URIs and classify WhatsApp message media."""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def encode_data_uri(data: bytes, mime: str) -> str:
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def ensure_data_uri(base64_or_uri: str, mime: str) -> str:
    if base64_or_uri.startswith("data:"):
        return base64_or_uri
    return f"data:{mime};base64,{base64_or_uri}"


def classify_message(message: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Return (kind, media_node) where kind is text|image|audio|document|sticker|unknown.
    """
    if "conversation" in message or "extendedTextMessage" in message:
        return "text", None
    if "imageMessage" in message:
        return "image", message.get("imageMessage")
    if "audioMessage" in message:
        return "audio", message.get("audioMessage")
    if "documentMessage" in message:
        return "document", message.get("documentMessage")
    if "documentWithCaptionMessage" in message:
        nested = message.get("documentWithCaptionMessage") or {}
        msg = nested.get("message") or nested
        return "document", msg.get("documentMessage") or msg
    if "stickerMessage" in message:
        return "sticker", message.get("stickerMessage")
    return "unknown", None


def extract_text_body(message: Dict[str, Any]) -> str:
    if "conversation" in message:
        return str(message.get("conversation") or "")
    ext = message.get("extendedTextMessage") or {}
    if isinstance(ext, dict) and ext.get("text"):
        return str(ext["text"])
    img = message.get("imageMessage") or {}
    if isinstance(img, dict) and img.get("caption"):
        return str(img["caption"])
    doc = message.get("documentMessage") or {}
    if isinstance(doc, dict) and doc.get("caption"):
        return str(doc["caption"])
    return ""


def document_is_pdf(media_node: Optional[Dict[str, Any]]) -> bool:
    if not media_node:
        return False
    mime = str(media_node.get("mimetype") or media_node.get("mime_type") or "").lower()
    name = str(media_node.get("fileName") or media_node.get("title") or "").lower()
    return "pdf" in mime or name.endswith(".pdf")
