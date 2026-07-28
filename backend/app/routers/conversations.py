"""Conversation listing endpoint."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ConversationSummary
from app.database.session import get_db
from app.memory.conversation_memory import ConversationMemory
from app.utils.security import verify_internal_api_key

router = APIRouter(tags=["conversations"], dependencies=[Depends(verify_internal_api_key)])


@router.get("/conversations", response_model=List[ConversationSummary])
async def list_conversations(db: AsyncSession = Depends(get_db)) -> List[ConversationSummary]:
    memory = ConversationMemory(db)
    rows = await memory.list_conversations()
    return [ConversationSummary(**row) for row in rows]
