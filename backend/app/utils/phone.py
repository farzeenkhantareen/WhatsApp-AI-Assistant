"""Phone number normalization for WhatsApp JIDs."""

import re


def normalize_phone(raw: str | None) -> str:
    """Extract digits-only international phone from JID or free-form input."""
    if not raw:
        return ""
    value = str(raw)
    if "@" in value:
        value = value.split("@", 1)[0]
    # Remove device suffixes like :12
    if ":" in value:
        value = value.split(":", 1)[0]
    digits = re.sub(r"\D", "", value)
    return digits


def to_whatsapp_jid(phone: str) -> str:
    """Build a WhatsApp JID from a normalized phone number."""
    normalized = normalize_phone(phone)
    if not normalized:
        raise ValueError("phone is required")
    return f"{normalized}@s.whatsapp.net"


def is_group_jid(jid: str | None) -> bool:
    """Return True if the remote JID is a group chat."""
    if not jid:
        return False
    return "@g.us" in jid or jid.endswith("@g.us")
