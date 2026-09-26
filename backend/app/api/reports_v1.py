"""
Product reports — how users flag listings (Google Play requires an in-app way to
report objectionable user-generated content).

A product reported by AUTO_HIDE_REPORTERS different users for a serious reason is
hidden automatically (moderation_status -> pending_review) until a human reviews it
with `python -m app.moderation_cli`.
"""

import logging
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.global_item import GlobalItem
from app.models.market import Market
from app.models.product_report import ProductReport
from app.models.user import User
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["Reports V1"])

AUTO_HIDE_REPORTERS = 3
AUTO_HIDE_REASONS = ("restricted_item", "offensive")


class ReportCreate(BaseModel):
    global_item_id: uuid.UUID
    market_id: Optional[uuid.UUID] = None
    reason: Literal["restricted_item", "wrong_info", "offensive", "spam", "other"]
    details: Optional[str] = Field(None, max_length=500)


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/hour")
async def report_product(
    request: Request,
    payload: ReportCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    gi = (await db.execute(
        select(GlobalItem).where(GlobalItem.id == payload.global_item_id)
    )).unique().scalar_one_or_none()
    if gi is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    market_id = payload.market_id
    if market_id is not None:
        exists = (await db.execute(select(Market.id).where(Market.id == market_id))).scalar_one_or_none()
        market_id = exists  # ignore unknown store ids instead of failing the report

    db.add(ProductReport(
        reporter_id=user.id,
        global_item_id=gi.id,
        market_id=market_id,
        reason=payload.reason,
        details=(payload.details or "").strip() or None,
    ))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()  # unique (reporter_id, global_item_id): one report per user per product
        return {"status": "already_reported"}

    serious = (await db.execute(
        select(func.count(func.distinct(ProductReport.reporter_id))).where(
            ProductReport.global_item_id == gi.id,
            ProductReport.status == "open",
            ProductReport.reason.in_(AUTO_HIDE_REASONS),
        )
    )).scalar_one()
    if serious >= AUTO_HIDE_REPORTERS and gi.moderation_status == "approved":
        gi.moderation_status = "pending_review"
        gi.restricted_reason = "user_reports"
        logger.warning("Product %s hidden for review after %d user reports", gi.id, serious)

    await db.commit()
    return {"status": "received"}
