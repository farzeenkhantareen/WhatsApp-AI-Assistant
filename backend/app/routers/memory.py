"""Memory management endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import MemoryDeleteResponse
from app.database.session import get_db
from app.memory.conversation_memory import ConversationMemory
from app.utils.phone import normalize_phone
from app.utils.security import verify_internal_api_key

router = APIRouter(tags=["memory"], dependencies=[Depends(verify_internal_api_key)])


@router.delete("/memory/{phone}", response_model=MemoryDeleteResponse)
async def delete_memory(
    phone: str,
    clear_postgres: bool = Query(
        False,
        description="If true, also delete permanent message history from PostgreSQL",
    ),
    db: AsyncSession = Depends(get_db),
) -> MemoryDeleteResponse:
    normalized = normalize_phone(phone)
    memory = ConversationMemory(db)
    result = await memory.clear_memory(normalized, clear_postgres=clear_postgres)
    detail = "Redis cache cleared"
    if clear_postgres:
        detail = "Redis cache and PostgreSQL history cleared"
    return MemoryDeleteResponse(
        phone=normalized,
        redis_cleared=result["redis_cleared"],
        postgres_cleared=result["postgres_cleared"],
        detail=detail,
    )
