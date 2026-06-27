"""
AlertService — Manages searching for and triggering user notifications when out-of-stock items go back in stock.
"""

import uuid
import logging
import numpy as np
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2 import Geometry, Geography
from geoalchemy2.elements import WKTElement

from app.models.market import Market
from app.models.global_item import GlobalItem
from app.models.market_item import MarketItem
from app.models.search_alert import SearchAlert

logger = logging.getLogger(__name__)


async def check_and_trigger_stock_alerts(db: AsyncSession, market_item_id: uuid.UUID) -> None:
    """
    Scans active search alerts within a 5km radius of the given market branch,
    and triggers mock notifications if the newly in-stock product has a
    cosine similarity score > 0.75 against the user's saved query vector.
    """
    # Query matching active search alerts within 5km of the market in a single join query.
    # This prevents SQLAlchemy type casting issues with python-bound geometry parameters.
    alerts_query = (
        select(
            SearchAlert,
            Market.name.label("market_name"),
            GlobalItem.name.label("item_name"),
            GlobalItem.text_embedding.label("item_embedding")
        )
        .select_from(SearchAlert)
        .join(Market, func.ST_DWithin(
            func.cast(Market.location, Geography),
            func.cast(
                func.ST_SetSRID(func.ST_Point(SearchAlert.longitude, SearchAlert.latitude), 4326),
                Geography
            ),
            5000.0
        ))
        .join(MarketItem, Market.id == MarketItem.market_id)
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .where(
            SearchAlert.is_active == True,
            MarketItem.id == market_item_id,
            MarketItem.status == True,
            MarketItem.stock_count > 0
        )
    )
    
    result = await db.execute(alerts_query)
    rows = result.all()
    
    if not rows:
        return
        
    for row in rows:
        alert, market_name, item_name, item_embedding = row[0], row[1], row[2], row[3]
        
        if item_embedding is None:
            continue
            
        product_vec = np.array(item_embedding)
        alert_vec = np.array(alert.query_vector)
        
        # Calculate Cosine Similarity
        dot_val = np.dot(product_vec, alert_vec)
        norm_p = np.linalg.norm(product_vec)
        norm_a = np.linalg.norm(alert_vec)
        
        similarity = dot_val / (norm_p * norm_a) if norm_p > 0 and norm_a > 0 else 0.0
        
        if similarity > 0.75:
            # Trigger mock push notification
            logger.info(
                f"[NOTIFICATION ENGINE] User alert triggered for user_id={alert.user_id}! "
                f"Your searched item '{alert.query_text}' is now IN STOCK: '{item_name}' "
                f"at store '{market_name}'! (Similarity: {similarity:.4f})"
            )
            # Deactivate alert to avoid repeat notification spam
            alert.is_active = False
            
    await db.flush()
