"""Logging helpers that redact secrets."""

import logging
import re
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)([^\"'\s]+)", re.I),
    re.compile(r"(authorization[\"']?\s*[:=]\s*[\"']?Bearer\s+)(\S+)", re.I),
    re.compile(r"(sk-or-v1-)[A-Za-z0-9]+", re.I),
]


def redact(value: str) -> str:
    """Redact sensitive tokens from a string."""
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: (m.group(1) if m.lastindex and m.lastindex >= 1 else "") + "***", redacted)
    return redacted


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def safe_extra(**kwargs: Any) -> dict[str, Any]:
    """Build a log extra dict with string values redacted."""
    out: dict[str, Any] = {}
    for key, value in kwargs.items():
        if isinstance(value, str):
            out[key] = redact(value)
        else:
            out[key] = value
    return out

# Centralized logging formatters

# Centralized logging formatters
