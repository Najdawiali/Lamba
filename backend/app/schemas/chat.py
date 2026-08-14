from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class StartConversationRequest(BaseModel):
    market_id: UUID
    product_id: Optional[UUID] = None
    message: Optional[str] = Field(None, max_length=2000)


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    id: UUID
    sender_id: UUID
    sender_name: Optional[str] = None
    is_me: bool = False
    text: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationListItem(BaseModel):
    id: UUID
    market_id: UUID
    market_name: str
    market_name_ar: Optional[str] = None
    product_name: Optional[str] = None
    product_name_ar: Optional[str] = None
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None

    class Config:
        from_attributes = True
