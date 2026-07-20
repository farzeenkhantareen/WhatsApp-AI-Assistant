"""Conversation memory: Postgres permanence + Redis recent window."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import get_settings
from app.database.redis_client import cache_delete, cache_get_json, cache_set_json
from app.models import Conversation, Message
from app.utils.phone import normalize_phone
from app.utils.sanitize import sanitize_text, truncate_payload

logger = logging.getLogger(__name__)


def _memory_key(phone: str) -> str:
    return f"memory:{normalize_phone(phone)}"


class ConversationMemory:
    """Orchestrates durable Postgres history and Redis hot cache."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def get_or_create_conversation(self, phone: str) -> Conversation:
        normalized = normalize_phone(phone)
        result = await self.session.execute(
            select(Conversation).where(Conversation.phone == normalized)
        )
        conversation = result.scalar_one_or_none()
        if conversation:
            return conversation
        conversation = Conversation(phone=normalized)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def append_message(
        self,
        phone: str,
        role: str,
        content: str,
        *,
        media_type: Optional[str] = None,
        media_url: Optional[str] = None,
        raw_payload: Optional[dict] = None,
    ) -> Message:
        conversation = await self.get_or_create_conversation(phone)
        message = Message(
            conversation_id=conversation.id,
            role=role,
            content=sanitize_text(content),
            media_type=media_type,
            media_url=media_url,
            raw_payload=truncate_payload(raw_payload),
        )
        conversation.updated_at = datetime.now(timezone.utc)
        self.session.add(message)
        await self.session.flush()
        await self._push_redis(phone, role, message.content, media_type=media_type)
        return message

    async def get_history_for_llm(self, phone: str) -> List[Dict[str, Any]]:
        """Prefer Redis window; fall back to Postgres and warm the cache."""
        cached = await cache_get_json(_memory_key(phone))
        if isinstance(cached, list) and cached:
            return cached[-self.settings.memory_window_size :]

        messages = await self.list_messages(phone, limit=self.settings.memory_window_size)
        history = [
            {
                "role": m.role if m.role in {"user", "assistant", "system", "tool"} else "user",
                "content": m.content,
                **({"media_type": m.media_type} if m.media_type else {}),
            }
            for m in messages
        ]
        if history:
            await cache_set_json(_memory_key(phone), history)
        return history

    async def list_messages(
        self, phone: str, *, limit: int = 100, offset: int = 0
    ) -> List[Message]:
        normalized = normalize_phone(phone)
        result = await self.session.execute(
            select(Message)
            .join(Conversation)
            .where(Conversation.phone == normalized)
            .order_by(Message.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_messages(self, phone: str) -> int:
        normalized = normalize_phone(phone)
        result = await self.session.execute(
            select(func.count(Message.id))
            .join(Conversation)
            .where(Conversation.phone == normalized)
        )
        return int(result.scalar_one())

    async def list_conversations(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        conversations = result.scalars().all()
        return [
            {
                "phone": c.phone,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "message_count": len(c.messages),
            }
            for c in conversations
        ]

    async def clear_memory(self, phone: str, *, clear_postgres: bool = False) -> Dict[str, bool]:
        redis_cleared = await cache_delete(_memory_key(phone))
        postgres_cleared = False
        if clear_postgres:
            conversation = await self.get_or_create_conversation(phone)
            await self.session.execute(
                delete(Message).where(Message.conversation_id == conversation.id)
            )
            await self.session.flush()
            postgres_cleared = True
        return {"redis_cleared": bool(redis_cleared), "postgres_cleared": postgres_cleared}

    async def _push_redis(
        self,
        phone: str,
        role: str,
        content: str,
        *,
        media_type: Optional[str] = None,
    ) -> None:
        key = _memory_key(phone)
        history = await cache_get_json(key)
        if not isinstance(history, list):
            history = []
        entry: Dict[str, Any] = {"role": role, "content": content}
        if media_type:
            entry["media_type"] = media_type
        history.append(entry)
        history = history[-self.settings.memory_window_size :]
        await cache_set_json(key, history)
