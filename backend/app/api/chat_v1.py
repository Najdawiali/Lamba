import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, desc
import sqlalchemy as sa
from uuid import UUID
from datetime import datetime, timezone

from app.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.market import Market
from app.models.market_item import MarketItem
from app.models.conversation import Conversation, Message
from app.models.global_item import GlobalItem
from app.schemas.chat import (
    StartConversationRequest, SendMessageRequest,
    MessageResponse, ConversationListItem,
)
from app.services.push_notifications import send_push_notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


@router.post("/conversations", status_code=201)
async def start_conversation(
    body: StartConversationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new conversation or return existing one, send first message."""
    # Check if conversation already exists
    result = await db.execute(
        select(Conversation).where(
            Conversation.customer_id == user.id,
            Conversation.market_id == body.market_id,
        )
    )
    conv = result.scalar_one_or_none()

    if conv is None:
        # Resolve product_id: mobile may send a market_items.id instead of global_items.id
        resolved_product_id = None
        if body.product_id:
            # First check if it's a valid global_items.id
            gi = await db.get(GlobalItem, body.product_id)
            if gi:
                resolved_product_id = gi.id
            else:
                # Try as a market_items.id and get its item_id (global_items FK)
                mi = await db.get(MarketItem, body.product_id)
                if mi:
                    resolved_product_id = mi.item_id

        # Create new conversation
        conv = Conversation(
            customer_id=user.id,
            market_id=body.market_id,
            product_id=resolved_product_id,
        )
        db.add(conv)
        await db.flush()
        conv_id = conv.id
    else:
        conv_id = conv.id

    # Only create a message if one was provided
    msg_id = None
    if body.message and body.message.strip():
        msg = Message(
            conversation_id=conv_id,
            sender_id=user.id,
            text=body.message,
        )
        db.add(msg)
        msg_id = str(msg.id)

        # Update conversation preview using raw SQL to avoid session issues
        await db.execute(
            sa.update(Conversation)
            .where(Conversation.id == conv_id)
            .values(
                last_message_text=body.message[:100],
                last_message_at=datetime.now(timezone.utc),
            )
        )

    await db.commit()

    # Send push notification to merchant only if a message was sent
    if msg_id:
        try:
            market_result = await db.execute(
                select(Market).where(Market.id == body.market_id)
            )
            market = market_result.scalar_one_or_none()
            if market and market.merchant_id:
                owner_result = await db.execute(
                    select(User).where(User.id == market.merchant_id)
                )
                owner = owner_result.scalar_one_or_none()
                if owner and owner.push_token:
                    await send_push_notification(
                        push_token=owner.push_token,
                        title="رسالة جديدة",
                        body=body.message[:100],
                        data={"conversation_id": str(conv_id), "type": "new_message"},
                    )
        except Exception as e:
            logger.warning(f"Push notification failed: {e}")

    return {"conversation_id": str(conv_id), "message_id": msg_id}


@router.get("/conversations", response_model=list[ConversationListItem])
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations for the current user."""
    # Find markets owned by this user
    owned_result = await db.execute(
        select(Market.id).where(Market.merchant_id == user.id)
    )
    owned_market_ids = [row[0] for row in owned_result.all()]

    # Conversations where user is customer OR market owner
    conditions = [Conversation.customer_id == user.id]
    if owned_market_ids:
        conditions.append(Conversation.market_id.in_(owned_market_ids))

    result = await db.execute(
        select(Conversation)
        .where(or_(*conditions))
        .order_by(desc(Conversation.last_message_at))
    )
    conversations = result.scalars().all()

    items = []
    for conv in conversations:
        market = await db.get(Market, conv.market_id)
        product = await db.get(GlobalItem, conv.product_id) if conv.product_id else None

        items.append(ConversationListItem(
            id=conv.id,
            market_id=conv.market_id,
            market_name=market.name if market else "Unknown",
            market_name_ar=getattr(market, 'name_ar', None),
            product_name=product.name if product else None,
            product_name_ar=getattr(product, 'name_ar', None),
            last_message=conv.last_message_text,
            last_message_at=conv.last_message_at,
        ))

    return items


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all messages in a conversation."""
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Verify access
    owned_result = await db.execute(
        select(Market.id).where(Market.merchant_id == user.id)
    )
    owned_ids = [row[0] for row in owned_result.all()]

    if conv.customer_id != user.id and conv.market_id not in owned_ids:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()

    items = []
    for msg in messages:
        sender = await db.get(User, msg.sender_id)
        items.append(MessageResponse(
            id=msg.id,
            sender_id=msg.sender_id,
            sender_name=getattr(sender, 'full_name', None),
            is_me=(msg.sender_id == user.id),
            text=msg.text,
            created_at=msg.created_at,
        ))

    return items


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse, status_code=201)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message in a conversation."""
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Verify access
    owned_result = await db.execute(
        select(Market.id).where(Market.merchant_id == user.id)
    )
    owned_ids = [row[0] for row in owned_result.all()]

    if conv.customer_id != user.id and conv.market_id not in owned_ids:
        raise HTTPException(status_code=403, detail="Access denied")

    customer_id = conv.customer_id
    market_id = conv.market_id

    msg = Message(
        conversation_id=conversation_id,
        sender_id=user.id,
        text=body.text,
    )
    db.add(msg)

    # Update conversation preview using sa.update
    await db.execute(
        sa.update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(
            last_message_text=body.text[:100],
            last_message_at=datetime.now(timezone.utc),
        )
    )

    await db.commit()

    # Notify the OTHER participant
    try:
        if user.id == customer_id:
            # Customer sent → notify merchant
            market = await db.get(Market, market_id)
            if market and market.merchant_id:
                owner = await db.get(User, market.merchant_id)
                if owner and owner.push_token:
                    await send_push_notification(
                        push_token=owner.push_token,
                        title="رسالة جديدة",
                        body=body.text[:100],
                        data={"conversation_id": str(conversation_id), "type": "new_message"},
                    )
        else:
            # Merchant sent → notify customer
            customer = await db.get(User, customer_id)
            if customer and customer.push_token:
                await send_push_notification(
                    push_token=customer.push_token,
                    title="رد من المتجر",
                    body=body.text[:100],
                    data={"conversation_id": str(conversation_id), "type": "new_message"},
                )
    except Exception as e:
        logger.warning(f"Push notification failed: {e}")

    return MessageResponse(
        id=msg.id,
        sender_id=user.id,
        sender_name=getattr(user, 'full_name', None),
        is_me=True,
        text=body.text,
        created_at=msg.created_at,
    )


@router.post("/push-token")
async def register_push_token(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register Expo push token for the current user."""
    token = body.get("token")
    if token:
        user.push_token = token
        await db.commit()
    return {"status": "ok"}
