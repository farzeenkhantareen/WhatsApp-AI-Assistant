"""Message history endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import MessageItem, MessagesResponse
from app.database.session import get_db
from app.memory.conversation_memory import ConversationMemory
from app.utils.phone import normalize_phone
from app.utils.security import verify_internal_api_key

router = APIRouter(tags=["messages"], dependencies=[Depends(verify_internal_api_key)])


@router.get("/messages/{phone}", response_model=MessagesResponse)
async def get_messages(
    phone: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> MessagesResponse:
    normalized = normalize_phone(phone)
    memory = ConversationMemory(db)
    messages = await memory.list_messages(normalized, limit=limit, offset=offset)
    total = await memory.count_messages(normalized)
    return MessagesResponse(
        phone=normalized,
        total=total,
        messages=[
            MessageItem(
                id=m.id,
                role=m.role,
                content=m.content,
                media_type=m.media_type,
                media_url=m.media_url,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )

# Import style updates

# Import style updates
