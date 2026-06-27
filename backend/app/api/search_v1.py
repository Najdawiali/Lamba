"""
Search V1 API — Hybrid Semantic + Proximity search and refinement fallback engine with Epic 6 enhancements.
"""

import uuid
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, File, Form, UploadFile
from geoalchemy2.elements import WKTElement
from geoalchemy2 import Geometry, Geography
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.market import Market
from app.models.global_item import GlobalItem
from app.models.market_item import MarketItem
from app.models.search_alert import SearchAlert
from app.schemas.search_v1 import (
    HybridSearchRequest,
    DoubleCheckSearchRequest,
    HybridSearchResponse,
    HybridSearchResultItem,
    SearchFilters,
)
from app.services.embedding import embedding_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/search", tags=["Search V1"])


async def _execute_hybrid_vector_query(
    query_vec: List[float],
    embedding_col,
    latitude: float,
    longitude: float,
    market_id: Optional[uuid.UUID],
    db: AsyncSession,
    limit: int = 15,
    min_similarity: float = 0.0,
    max_similarity: float = 1.0,
    filters: Optional[SearchFilters] = None,
    lexical_queries: Optional[List[str]] = None,
) -> List[HybridSearchResultItem]:
    """
    Core reusable routine running a weighted rank query combining semantic pgvector
    correlation, PostGIS geography metric distance, and multi-criteria faceted search filters.
    """
    # Build WKT POINT for user location
    point_wkt = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
    geog_location = Market.location.cast(Geography)
    geog_point = func.cast(point_wkt, Geography)
    
    # Proximity expressions
    distance_km_expr = (func.ST_Distance(geog_location, geog_point) / 1000.0)
    
    # Semantic similarity expression (1.0 - cosine_distance yields Cosine Similarity)
    cosine_dist_expr = embedding_col.cosine_distance(query_vec)
    semantic_score_expr = func.coalesce(1.0 - cosine_dist_expr, 0.0)
    
    # Build lexical match conditions and score boosts for exact matches
    lexical_cond = None
    if lexical_queries:
        from sqlalchemy import or_
        conds = []
        for q in lexical_queries:
            if q and q.strip():
                term = f"%{q.strip()}%"
                conds.append(GlobalItem.name.ilike(term))
                conds.append(GlobalItem.description.ilike(term))
        if conds:
            lexical_cond = or_(*conds)
            
    # Apply a 0.5 score boost if the query matches the product name or description lexically
    if lexical_cond is not None:
        from sqlalchemy import case
        boosted_semantic_score_expr = semantic_score_expr + case(
            (lexical_cond, 0.5),
            else_=0.0
        )
    else:
        boosted_semantic_score_expr = semantic_score_expr
        
    # Handle custom radius or default to 5km limit
    max_dist_km = 5.0
    if filters and filters.max_distance_km is not None:
        max_dist_km = filters.max_distance_km
    radius_meters = max_dist_km * 1000.0
    
    proximity_score_expr = func.greatest(0.0, 1.0 - (distance_km_expr / max_dist_km))
    
    # Scoring configurations (Local vs Global)
    if market_id:
        # Local Shop Search: 100% semantic weight, no geo filter
        final_score_expr = boosted_semantic_score_expr
    else:
        # Global Search: (0.7 * semantic) + (0.3 * proximity)
        final_score_expr = (0.7 * boosted_semantic_score_expr) + (0.3 * proximity_score_expr)
        
    # Build core SQL statement
    where_cond = (semantic_score_expr >= min_similarity) & (semantic_score_expr <= max_similarity)
    if lexical_cond is not None:
        from sqlalchemy import or_
        where_cond = or_(where_cond, lexical_cond)
        
    stmt = (
        select(
            MarketItem,
            GlobalItem,
            Market,
            func.ST_Y(Market.location.cast(Geometry)).label("lat"),
            func.ST_X(Market.location.cast(Geometry)).label("lng"),
            distance_km_expr.label("distance_km"),
            boosted_semantic_score_expr.label("semantic_score"),
            proximity_score_expr.label("proximity_score"),
            final_score_expr.label("final_score")
        )
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .options(
            selectinload(GlobalItem.category_rel),
            selectinload(GlobalItem.images)
        )
        .where(
            embedding_col.is_not(None),
            where_cond
        )
    )
    
    # Apply standard status/stock filters
    if filters and filters.in_stock_only:
        stmt = stmt.where(MarketItem.status == True, MarketItem.stock_count > 0)
    else:
        # Show all active items (including out-of-stock)
        stmt = stmt.where(MarketItem.status == True)
        
    # Apply dynamic filters
    if filters:
        if filters.business_nature:
            stmt = stmt.where(Market.business_nature.ilike(f"%{filters.business_nature}%"))
        if filters.category_id:
            stmt = stmt.where(GlobalItem.category_id == filters.category_id)
        if filters.price_min is not None:
            stmt = stmt.where(MarketItem.price >= filters.price_min)
        if filters.price_max is not None:
            stmt = stmt.where(MarketItem.price <= filters.price_max)
        if filters.city:
            stmt = stmt.where(Market.address.ilike(f"%{filters.city}%"))
        
    # Apply bounds
    if market_id:
        stmt = stmt.where(MarketItem.market_id == market_id)
    else:
        stmt = stmt.where(func.ST_DWithin(geog_location, geog_point, radius_meters))
        
    # Order by final score descending and limit results to top matches
    stmt = stmt.order_by(final_score_expr.desc()).limit(limit)
    
    result = await db.execute(stmt)
    rows = result.unique().all()
    
    # Run dynamic schedule update to ensure freshness of returned stores
    unique_markets = list({row[2].id: row[2] for row in rows}.values())
    if unique_markets:
        from app.utils.schedule import check_and_update_markets_schedule
        await check_and_update_markets_schedule(db, unique_markets)
        
    enriched_items = []
    for row in rows:
        mi, gi, market, lat, lng, dist_km, sem_score, prox_score, fin_score = row
        price_val = getattr(mi, "price", None)
        if price_val is not None:
            price_val = float(price_val)
        
        enriched_items.append(
            HybridSearchResultItem(
                item_id=gi.id,
                market_item_id=mi.id,
                name=gi.name,
                description=gi.description,
                category=gi.category,
                image_url=gi.image_url,
                price=price_val,
                stock_count=mi.stock_count,
                in_stock=mi.status,
                market_id=market.id,
                market_name=market.name,
                market_address=market.address,
                latitude=float(lat),
                longitude=float(lng),
                market_is_open=market.is_currently_open,
                distance_km=round(float(dist_km), 2),
                semantic_score=round(float(sem_score), 4),
                proximity_score=round(float(prox_score), 4),
                final_score=round(float(fin_score), 4)
            )
        )
        
    return enriched_items


def _filter_top_five_unless_accuracy_above_80(results: List[HybridSearchResultItem]) -> List[HybridSearchResultItem]:
    """
    Retrieve the top five matches when the user searches for an item,
    unless the retrieved items' accuracy (semantic_score) is above 80% (i.e. >= 0.80).
    If there are 5 or more items with accuracy >= 0.80, we return all of them.
    Otherwise, we return the top 5 matches.
    """
    above_80 = [r for r in results if r.semantic_score >= 0.80]
    if len(above_80) >= 5:
        return above_80
    return results[:5]



# ── POST /hybrid ────────────────────────────────────────────────
@router.post("/hybrid", response_model=HybridSearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Perform hybrid vector search combining semantic text embeddings (pgvector)
    and metric geographical proximity (PostGIS) with advanced faceted filtering.
    Falls back to semantic proximity recommendations if zero exact results are found.
    """
    try:
        # Generate 384-dimensional normalized text vector
        query_vec = embedding_service.encode_text_384(request.query_text).tolist()
        
        # Translate query in both directions to match lexically across languages
        from app.services.translation import translate_ar_to_en, translate_en_to_ar
        original_query = request.query_text
        query_en = translate_ar_to_en(original_query)
        query_ar = translate_en_to_ar(original_query)
        
        lexical_queries = list(set(filter(None, [original_query, query_en, query_ar])))
        
        # 1. Exact Matches search (cosine similarity >= 0.65 or exact lexical match)
        results = await _execute_hybrid_vector_query(
            query_vec=query_vec,
            embedding_col=GlobalItem.text_embedding,
            latitude=request.latitude,
            longitude=request.longitude,
            market_id=request.market_id,
            db=db,
            min_similarity=0.65,
            filters=request.filters,
            lexical_queries=lexical_queries
        )
        
        search_mode = "exact_matches"
        action = None
        
        if results:
            results = _filter_top_five_unless_accuracy_above_80(results)
            found = True
        else:
            found = False
        
        # 2. recommendations Fallback loop if zero exact matches
        if not results:
            results = await _execute_hybrid_vector_query(
                query_vec=query_vec,
                embedding_col=GlobalItem.text_embedding,
                latitude=request.latitude,
                longitude=request.longitude,
                market_id=request.market_id,
                db=db,
                min_similarity=0.40,
                max_similarity=0.64,
                filters=request.filters,
                lexical_queries=lexical_queries
            )
            if results:
                results = _filter_top_five_unless_accuracy_above_80(results)
                search_mode = "recommendations"
                action = "recommendations"
                found = True
            else:
                found = False
                action = "request_more_details"
                
                # 3. Create SearchAlert to cache failed search query for customer notifications
                user_id = request.user_id
                if user_id:
                    alert = SearchAlert(
                        user_id=user_id,
                        query_text=request.query_text,
                        query_vector=query_vec,
                        latitude=request.latitude,
                        longitude=request.longitude,
                        is_active=True
                    )
                    db.add(alert)
                    await db.flush()
                    logger.info(f"[SEARCH ALERT ENGINE] Cached search alert for user={user_id} term='{request.query_text}'")
            
        return HybridSearchResponse(
            found=found,
            action=action,
            search_mode=search_mode,
            results=results
        )
        
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during search execution: {str(e)}",
        )


# ── POST /image ─────────────────────────────────────────────────
@router.post("/image", response_model=HybridSearchResponse)
async def image_search(
    image: UploadFile = File(..., description="Product image to search for"),
    latitude: float = Form(...),
    longitude: float = Form(...),
    market_id: Optional[uuid.UUID] = Form(None),
    limit: int = Form(15),
    radius_km: Optional[float] = Form(None),
    in_stock_only: Optional[bool] = Form(None),
    price_min: Optional[float] = Form(None),
    price_max: Optional[float] = Form(None),
    business_nature: Optional[str] = Form(None),
    category_id: Optional[uuid.UUID] = Form(None),
    city: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Perform hybrid visual search using Gemma VLM brand/label recognition
    mapped to high-precision hybrid text vector search, with raw CLIP
    image embedding cross-modal matching as a fail-safe.
    """
    if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, and WebP images are supported",
        )
    try:
        # Read image bytes
        image_bytes = await image.read()
        
        filters = None
        if (radius_km is not None or in_stock_only is not None or price_min is not None or 
            price_max is not None or business_nature is not None or category_id is not None or city is not None):
            filters = SearchFilters(
                max_distance_km=radius_km,
                in_stock_only=in_stock_only,
                price_min=price_min,
                price_max=price_max,
                business_nature=business_nature,
                category_id=category_id,
                city=city
            )

        results = []
        vlm_query = None

        # 1. Gemma VLM Brand & Label Recognition
        if embedding_service.gemma_processor is not None and embedding_service.gemma_model is not None:
            logger.info("[IMAGE SEARCH] Gemma VLM is loaded. Running visual product identification...")
            vlm_query = embedding_service.identify_product_from_image(image_bytes)
            if vlm_query and vlm_query.strip():
                logger.info(f"[IMAGE SEARCH] VLM identified: '{vlm_query}'. Executing text hybrid search.")
                
                # Generate 384-dimensional normalized text vector
                query_vector = embedding_service.encode_text_384(vlm_query).tolist()
                
                # Get bidirectional translations for exact lexical matching
                from app.services.translation import translate_ar_to_en, translate_en_to_ar
                query_en = translate_ar_to_en(vlm_query)
                query_ar = translate_en_to_ar(vlm_query)
                lexical_queries = list(set(filter(None, [vlm_query, query_en, query_ar])))
                
                results = await _execute_hybrid_vector_query(
                    query_vec=query_vector,
                    embedding_col=GlobalItem.text_embedding,
                    latitude=latitude,
                    longitude=longitude,
                    market_id=market_id,
                    db=db,
                    limit=limit,
                    filters=filters,
                    lexical_queries=lexical_queries
                )

        # 2. CLIP Cross-Modal Visual Fallback
        if not results:
            if vlm_query:
                logger.info(f"[IMAGE SEARCH] VLM search for '{vlm_query}' returned 0 results. Falling back to raw CLIP.")
            else:
                logger.info("[IMAGE SEARCH] VLM query not available. Executing raw CLIP search.")
                
            query_vector = embedding_service.encode_image_bytes(image_bytes).tolist()
            results = await _execute_hybrid_vector_query(
                query_vec=query_vector,
                embedding_col=GlobalItem.image_embedding,
                latitude=latitude,
                longitude=longitude,
                market_id=market_id,
                db=db,
                limit=limit,
                filters=filters
            )
        
        results = _filter_top_five_unless_accuracy_above_80(results)
        
        return HybridSearchResponse(
            found=len(results) > 0,
            action=None if len(results) > 0 else "request_more_details",
            search_mode="exact_matches",
            results=results
        )
        
    except Exception as e:
        logger.error(f"Hybrid image search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during visual search: {str(e)}",
        )


# ── POST /double-check ──────────────────────────────────────────
@router.post("/double-check", response_model=HybridSearchResponse)
async def double_check_search(
    request: DoubleCheckSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Secondary fallback search endpoint concatenating original query and user refined details
    to recalculate a richer text embedding and re-evaluate matches.
    """
    try:
        # Combine text components for richer contextual details
        refined_query = f"{request.original_query_text.strip()} {request.user_refined_details.strip()}"
        query_vec = embedding_service.encode_text_384(refined_query).tolist()
        
        # Translate query in both directions to match lexically across languages
        from app.services.translation import translate_ar_to_en, translate_en_to_ar
        lexical_queries = list(set(filter(None, [
            request.original_query_text,
            request.user_refined_details,
            translate_ar_to_en(refined_query),
            translate_en_to_ar(refined_query)
        ])))
        
        results = await _execute_hybrid_vector_query(
            query_vec=query_vec,
            embedding_col=GlobalItem.text_embedding,
            latitude=request.latitude,
            longitude=request.longitude,
            market_id=request.market_id,
            db=db,
            lexical_queries=lexical_queries
        )
        
        results = _filter_top_five_unless_accuracy_above_80(results)
        
        # Explicit zero-results flag structure if still empty
        return HybridSearchResponse(
            found=len(results) > 0,
            action=None if len(results) > 0 else "zero_results",
            search_mode="exact_matches",
            results=results
        )
        
    except Exception as e:
        logger.error(f"Fallback double-check search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during refined search execution: {str(e)}",
        )
