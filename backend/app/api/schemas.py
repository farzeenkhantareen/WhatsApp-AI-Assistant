"""Pydantic request/response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    database: bool
    redis: bool
    evolution: bool
    instance: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class SendMessageRequest(BaseModel):
    phone: str = Field(..., description="Recipient phone number in international format")
    message: Optional[str] = Field(None, description="Text body")
    media_url: Optional[str] = None
    media_type: Optional[str] = Field(None, description="image | document | pdf")
    file_name: Optional[str] = None
    caption: Optional[str] = None
    model: Optional[str] = Field(None, description="Optional OpenRouter model override (unused for raw send)")


class SendMessageResponse(BaseModel):
    success: bool
    phone: str
    detail: str


class ConversationSummary(BaseModel):
    phone: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    created_at: datetime


class MessagesResponse(BaseModel):
    phone: str
    messages: List[MessageItem]
    total: int


class MemoryDeleteResponse(BaseModel):
    phone: str
    redis_cleared: bool
    postgres_cleared: bool
    detail: str


class WebhookAck(BaseModel):
    received: bool = True
    processed: bool = False
    detail: str = "ok"
