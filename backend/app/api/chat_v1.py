from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import or_, desc, func
import uuid
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.api.auth import get_current_user
from app.models import User, Market, ChatSession, ChatMessage

router = APIRouter(tags=["Chat V1"])

# ── Pydantic Schemas ─────────────────────────────────────────

class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    sender_id: uuid.UUID
    text: str
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class ChatSessionResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    market_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    # Optional fields for UI convenience
    partner_name: str | None = None
    last_message: str | None = None
    unread_count: int = 0

    class Config:
        from_attributes = True

class SendMessageRequest(BaseModel):
    text: str

# ── Endpoints ───────────────────────────────────────────────

@router.post("/chat/start/{market_id}", response_model=ChatSessionResponse)
async def start_or_get_chat_session(
    market_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Start a new chat session with a market, or return the existing one.
    Only customers should initiate chats with markets.
    """
    if user.user_type != "customer":
        raise HTTPException(status_code=403, detail="Only customers can initiate a chat with a market.")
        
    # Check if market exists
    market_result = await db.execute(select(Market).where(Market.id == market_id))
    market = market_result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found.")
        
    # Check for existing session
    session_result = await db.execute(
        select(ChatSession).where(
            ChatSession.customer_id == user.id,
            ChatSession.market_id == market_id
        )
    )
    chat_session = session_result.scalar_one_or_none()
    
    if not chat_session:
        # Create a new session
        chat_session = ChatSession(
            customer_id=user.id,
            market_id=market_id
        )
        db.add(chat_session)
        await db.commit()
        await db.refresh(chat_session)
        
    response = ChatSessionResponse.model_validate(chat_session)
    response.partner_name = market.name
    return response


@router.get("/chat/sessions", response_model=List[ChatSessionResponse])
async def list_chat_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all active chat sessions.
    - If customer: returns sessions where they are the customer_id.
    - If merchant: returns sessions for their market(s).
    """
    if user.user_type == "customer":
        stmt = select(ChatSession).where(ChatSession.customer_id == user.id).options(selectinload(ChatSession.market))
        result = await db.execute(stmt)
        sessions = result.scalars().all()
        
        responses = []
        for s in sessions:
            r = ChatSessionResponse.model_validate(s)
            r.partner_name = s.market.name if s.market else "Unknown Market"

            # Get last message
            msg_stmt = select(ChatMessage).where(ChatMessage.session_id == s.id).order_by(desc(ChatMessage.created_at)).limit(1)
            msg_res = await db.execute(msg_stmt)
            last_msg = msg_res.scalar_one_or_none()
            if last_msg:
                r.last_message = last_msg.text

            # Unread count = messages from the other side not yet read by this customer
            unread_stmt = (
                select(func.count(ChatMessage.id))
                .where(
                    ChatMessage.session_id == s.id,
                    ChatMessage.sender_id != user.id,
                    ChatMessage.is_read == False,
                )
            )
            unread_res = await db.execute(unread_stmt)
            r.unread_count = unread_res.scalar() or 0

            responses.append(r)

        return responses

    elif user.user_type == "merchant":
        # Find merchant's markets
        market_res = await db.execute(select(Market).where(Market.merchant_id == user.id))
        market = market_res.scalar_one_or_none()
        if not market:
            return []
            
        stmt = select(ChatSession).where(ChatSession.market_id == market.id).options(selectinload(ChatSession.customer))
        result = await db.execute(stmt)
        sessions = result.scalars().all()
        
        responses = []
        for s in sessions:
            r = ChatSessionResponse.model_validate(s)
            r.partner_name = s.customer.email or s.customer.phone_number or "Customer"

            # Get last message
            msg_stmt = select(ChatMessage).where(ChatMessage.session_id == s.id).order_by(desc(ChatMessage.created_at)).limit(1)
            msg_res = await db.execute(msg_stmt)
            last_msg = msg_res.scalar_one_or_none()
            if last_msg:
                r.last_message = last_msg.text

            # Unread count = messages from the customer not yet read by this merchant
            unread_stmt = (
                select(func.count(ChatMessage.id))
                .where(
                    ChatMessage.session_id == s.id,
                    ChatMessage.sender_id != user.id,
                    ChatMessage.is_read == False,
                )
            )
            unread_res = await db.execute(unread_stmt)
            r.unread_count = unread_res.scalar() or 0

            responses.append(r)

        return responses
    
    return []


@router.get("/chat/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_chat_messages(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch all messages in a specific chat session.
    """
    # Verify participant
    session_res = await db.execute(select(ChatSession).where(ChatSession.id == session_id).options(selectinload(ChatSession.market)))
    chat_session = session_res.scalar_one_or_none()
    
    if not chat_session:
        raise HTTPException(status_code=404, detail="Chat session not found.")
        
    if user.user_type == "customer" and chat_session.customer_id != user.id:
        raise HTTPException(status_code=403, detail="Not a participant.")
    
    if user.user_type == "merchant" and chat_session.market.merchant_id != user.id:
        raise HTTPException(status_code=403, detail="Not a participant.")
        
    stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    result = await db.execute(stmt)
    messages = result.scalars().all()
    
    return messages


@router.post("/chat/sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def send_chat_message(
    session_id: uuid.UUID,
    request: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Send a message in a chat session.
    """
    # Verify participant
    session_res = await db.execute(select(ChatSession).where(ChatSession.id == session_id).options(selectinload(ChatSession.market)))
    chat_session = session_res.scalar_one_or_none()
    
    if not chat_session:
        raise HTTPException(status_code=404, detail="Chat session not found.")
        
    if user.user_type == "customer" and chat_session.customer_id != user.id:
        raise HTTPException(status_code=403, detail="Not a participant.")
    
    if user.user_type == "merchant" and chat_session.market.merchant_id != user.id:
        raise HTTPException(status_code=403, detail="Not a participant.")
        
    msg = ChatMessage(
        session_id=session_id,
        sender_id=user.id,
        text=request.text
    )
    db.add(msg)
    
    # Update session updated_at
    from datetime import datetime, timezone
    chat_session.updated_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(msg)
    
    return msg
