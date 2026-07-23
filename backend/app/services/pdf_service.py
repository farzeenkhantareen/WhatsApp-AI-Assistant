"""PDF text extraction and analysis helpers."""

from __future__ import annotations

import base64
import io
import logging
from typing import Optional

from pypdf import PdfReader

from app.services.openrouter_client import openrouter_client
from app.utils.sanitize import sanitize_text

logger = logging.getLogger(__name__)

MAX_PDF_CHARS = 12000


def extract_pdf_text_from_base64(b64: str, *, max_chars: int = MAX_PDF_CHARS) -> str:
    """Decode base64 PDF and extract text."""
    raw = b64
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    data = base64.b64decode(raw)
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("PDF page extract failed: %s", exc)
    text = "\n".join(parts).strip()
    text = sanitize_text(text, max_length=max_chars)
    if not text:
        return "[PDF contained no extractable text]"
    return text


async def summarize_pdf_text(
    text: str,
    *,
    user_prompt: Optional[str] = None,
    system: Optional[str] = None,
) -> str:
    """Ask the LLM to analyze extracted PDF text."""
    prompt = user_prompt or "Summarize the key points of this document and answer any questions."
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append(
        {
            "role": "user",
            "content": f"{prompt}\n\n--- DOCUMENT TEXT ---\n{text}",
        }
    )
    return await openrouter_client.complete_text(messages)
