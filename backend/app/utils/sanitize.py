"""Sanitization helpers for untrusted user input."""

import re
import unicodedata

from app.config.settings import get_settings

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(text: str | None, max_length: int | None = None) -> str:
    """Strip control characters, normalize unicode, and truncate."""
    if text is None:
        return ""
    settings = get_settings()
    limit = max_length or settings.max_user_message_length
    cleaned = unicodedata.normalize("NFKC", str(text))
    cleaned = _CONTROL_CHARS.sub("", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) > limit:
        cleaned = cleaned[:limit]
    return cleaned


def truncate_payload(payload: dict | None, max_chars: int = 4000) -> dict | None:
    """Return a shallow-copied payload with oversized string values truncated."""
    if payload is None:
        return None
    out: dict = {}
    for key, value in payload.items():
        if isinstance(value, str) and len(value) > max_chars:
            out[key] = value[:max_chars] + "...[truncated]"
        elif isinstance(value, dict):
            out[key] = truncate_payload(value, max_chars=max_chars)
        else:
            out[key] = value
    return out
