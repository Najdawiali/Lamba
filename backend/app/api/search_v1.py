"""
Search V1 API — Hybrid Qwen3 semantic + PostGIS proximity + Arabic tsvector lexical,
with BGE-reranker-v2-m3 cross-encoder refinement.

Pipeline (text-only stack):
  1. Normalize the query (Arabic NFKC + alef/hamza unification + Arabizi → Arabic).
  2. Embed via Qwen3-Embedding-0.6B (1024-d, multilingual — no AR→EN pretranslation).
  3. SQL hybrid retrieval in Postgres:
       cosine_distance(text_embedding, query_vec)  over HNSW  (semantic)
       search_tsv @@ plainto_tsquery(normalized_q)            (lexical, GIN)
       ST_DWithin(location, point, radius) over PostGIS         (proximity)
     Combined final_score = 0.7*semantic + 0.3*proximity  (global)
                         = 1.0*semantic                  (in-shop)
  4. Top-30 candidates → BGE-reranker-v2-m3 cross-encoder  (GPU, ~5ms)
     Recompute final_score = 0.6*rerank + 0.4*prior.
  5. Two-tier fallback:  ≥0.65 exact → 0.40–0.64 recommendations → SearchAlert cache.
  6. Top-5 cap, unless ≥5 results already score ≥0.80.

Image search endpoint (/image) is hidden in this phase — returns 410 Gone
until settings.enable_image_search is flipped on.
"""

import uuid
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, File, Form, UploadFile
from geoalchemy2.elements import WKTElement
from geoalchemy2 import Geometry, Geography
from sqlalchemy import select, func, or_, text as sql_text
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.api.auth import get_current_user
from app.models.market import Market
from app.models.global_item import GlobalItem
from app.models.market_item import MarketItem
from app.models.user import User
from app.models.search_alert import SearchAlert
from app.schemas.search_v1 import (
    HybridSearchRequest,
    DoubleCheckSearchRequest,
    HybridSearchResponse,
    HybridSearchResultItem,
    SearchFilters,
)
from app.services.embedding import embedding_service
from app.services.reranker import reranker_service
from app.services.arabic_norm import normalize_query, normalize_arabic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/search", tags=["Search V1"])

# Latest semantic accuracy stats by the reranker can be 0.5..1.5 before the
# extraction cap, so the cap only acts once scores are normalized.
RETRIEVAL_TOP_K = (
    settings.reranker_top_k if settings.enable_reranker else settings.reranker_final_k
)


async def _execute_hybrid_vector_query(
    query_vec: List[float],
    latitude: float,
    longitude: float,
    market_id: Optional[uuid.UUID],
    db: AsyncSession,
    limit: int = RETRIEVAL_TOP_K,
    min_similarity: float = 0.0,
    max_similarity: float = 1.0,
    filters: Optional[SearchFilters] = None,
    lexical_query_normalized: Optional[str] = None,
) -> List[HybridSearchResultItem]:
    """
    Hybrid SQL retrieval combining pgvector semantic match + PostGIS proximity
    + Arabic tsvector lexical match. Returns up to `limit` candidates for the
    reranker to refine.
    """
    point_wkt = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
    geog_location = Market.location.cast(Geography)
    geog_point = func.cast(point_wkt, Geography)

    distance_km_expr = (func.ST_Distance(geog_location, geog_point) / 1000.0)

    cosine_dist_expr = GlobalItem.text_embedding.cosine_distance(query_vec)
    semantic_score_expr = func.coalesce(1.0 - cosine_dist_expr, 0.0)

    # Lexical match via tsvector @@ plainto_tsquery (replaces the old ILIKE scan).
    # The generated search_tsv combines 'arabic' and 'simple' configs so cross-script
    # lookups like شاي ↔ "tea" surface through the enriched search_terms column.
    # We OR-union the two tsqueries (`||`) into one so a single ts_rank call scores
    # both scripts at once.
    lexical_cond = None
    lexical_rank_expr = func.coalesce(sql_text("0"), 0.0)
    if lexical_query_normalized:
        tsquery = func.plainto_tsquery("arabic", lexical_query_normalized).op("||")(
            func.plainto_tsquery("simple", lexical_query_normalized)
        )
        lexical_cond = GlobalItem.search_tsv.op("@@")(tsquery)
        lexical_rank_expr = func.ts_rank(GlobalItem.search_tsv, tsquery)

    # Lexical-boosted semantic score — match-aware. Replaces the old 0.5 case-on
    # ILIKE boost with a continuous ts_rank contribution scaled to the same order.
    if lexical_cond is not None:
        from sqlalchemy import case
        boosted_semantic_score_expr = semantic_score_expr + case(
            (lexical_cond, 0.5 + func.least(0.3, lexical_rank_expr)),
            else_=0.0
        )
    else:
        boosted_semantic_score_expr = semantic_score_expr

    # Handle custom radius or default to 5km limit
    max_dist_km = settings.default_search_radius_km
    if filters and filters.max_distance_km is not None and filters.max_distance_km > 0:
        max_dist_km = filters.max_distance_km
    radius_meters = max_dist_km * 1000.0

    proximity_score_expr = func.greatest(0.0, 1.0 - (distance_km_expr / max_dist_km))

    if market_id:
        final_score_expr = boosted_semantic_score_expr
    else:
        final_score_expr = (0.7 * boosted_semantic_score_expr) + (0.3 * proximity_score_expr)

    # Combined WHERE: semantic OR lexical (semantic branch requires embedding non-null).
    semantic_cond = (
        GlobalItem.text_embedding.is_not(None)
        & (semantic_score_expr >= min_similarity)
        & (semantic_score_expr <= max_similarity)
    )
    if lexical_cond is not None:
        where_cond = or_(semantic_cond, lexical_cond)
    else:
        where_cond = semantic_cond

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
            final_score_expr.label("final_score"),
        )
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .options(
            selectinload(GlobalItem.category_rel),
            selectinload(GlobalItem.images),
        )
        .where(where_cond)
    )

    if filters and filters.in_stock_only:
        stmt = stmt.where(MarketItem.status == True, MarketItem.stock_count > 0)
    else:
        stmt = stmt.where(MarketItem.status == True)

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
            # Normalize both sides: replace punctuation/whitespace with a single
            # wildcard so "As Salt" / "As-Salt" / "As_Salt" all match each other.
            # ILIKE is case-insensitive but not punctuation-insensitive, so we
            # collapse separators into `%` around the cleaned token.
            import re as _re
            city_token = _re.sub(r"[\s\-_]+", "%", filters.city.strip().lower())
            stmt = stmt.where(
                func.lower(Market.address).op("LIKE")(f"%{city_token}%")
            )

    if market_id:
        stmt = stmt.where(MarketItem.market_id == market_id)
    else:
        stmt = stmt.where(func.ST_DWithin(geog_location, geog_point, radius_meters))

    stmt = stmt.order_by(final_score_expr.desc()).limit(limit)

    result = await db.execute(stmt)
    rows = result.unique().all()

    unique_markets = list({row[2].id: row[2] for row in rows}.values())
    if unique_markets:
        from app.utils.schedule import check_and_update_markets_schedule
        try:
            await check_and_update_markets_schedule(db, unique_markets)
        except Exception as e:
            logger.warning(f"Schedule refresh skipped: {e}")

    items: List[HybridSearchResultItem] = []
    import math as _m
    for row in rows:
        mi, gi, market, lat, lng, dist_km, sem_score, prox_score, fin_score = row
        price_val = float(mi.price) if getattr(mi, "price", None) is not None else None

        def _safe(v, default=0.0):
            try:
                fv = float(v)
            except (TypeError, ValueError):
                return default
            if _m.isnan(fv) or _m.isinf(fv):
                return default
            return fv

        items.append(
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
                distance_km=round(_safe(dist_km), 2),
                semantic_score=round(_safe(sem_score), 4),
                proximity_score=round(_safe(prox_score), 4),
                final_score=round(_safe(fin_score), 4),
            )
        )
    return items


def _filter_top_five_unless_accuracy_above_80(
    results: List[HybridSearchResultItem],
) -> List[HybridSearchResultItem]:
    """
    Top-5 cap, unless we already have ≥5 results scoring ≥0.80 — in which case
    return all ≥0.80 matches (lets a broad category query surface a full shelf).
    """
    above_80 = [r for r in results if r.semantic_score >= 0.80]
    if len(above_80) >= 5:
        return above_80
    return results[:5]


async def _rerank_candidates(
    query_text: str,
    results: List[HybridSearchResultItem],
) -> List[HybridSearchResultItem]:
    """
    Pass top-N candidates through the Qwen3-Reranker cross-encoder.

    The reranker adjusts `final_score` = 0.6 * rerank + 0.4 * prior_sql,
    re-sorts decreasing, and keeps up to `settings.reranker_final_k`.
    If the reranker is unavailable or disabled, returns results unchanged.
    """
    if not settings.enable_reranker or not results:
        return results

    candidates = []
    for r in results:
        text_parts = [r.name]
        if r.description:
            text_parts.append(r.description)
        candidates.append({
            "text": " ".join(text_parts),
            "final_score": r.final_score,
            "semantic_score": r.semantic_score,
            "result": r,
        })

    reranked = await reranker_service.rerank_async(
        query=query_text,
        candidates=candidates,
        top_k=settings.reranker_final_k,
    )
    out: List[HybridSearchResultItem] = []
    for c in reranked:
        r = c["result"]
        r.final_score = float(c.get("final_score", r.final_score))
        # Use rerank score as a proxy for an updated semantic_score so
        # _filter_top_five_unless_accuracy_above_80 still gates meaningfully.
        r.semantic_score = float(c.get("rerank_score", r.semantic_score))
        out.append(r)
    return out


# ── POST /hybrid ────────────────────────────────────────────────
@router.post("/hybrid", response_model=HybridSearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hybrid text search: Qwen3 semantic + PostGIS proximity + Arabic tsvector lexical,
    refined by BGE-reranker-v2-m3. Two-tier fallback (exact → recommendations → alert).
    """
    try:
        # 1. Normalize the raw query (Arabic NFKC + Arabizi → Arabic + lowercase).
        normalized_query = normalize_query(request.query_text)

        # 2. Embed via Qwen3 (no AR→EN pretranslation — encoder is multilingual).
        query_vec = (await embedding_service.encode_text_async(
            normalized_query or request.query_text
        )).tolist()

        # 3. Exact tier: cosine ≥ 0.65 OR lexical tsvector match.
        results = await _execute_hybrid_vector_query(
            query_vec=query_vec,
            latitude=request.latitude,
            longitude=request.longitude,
            market_id=request.market_id,
            db=db,
            min_similarity=0.65,
            filters=request.filters,
            lexical_query_normalized=normalized_query,
        )

        search_mode = "exact_matches"
        action = None
        found = bool(results)

        if found:
            results = await _rerank_candidates(request.query_text, results)
            results = _filter_top_five_unless_accuracy_above_80(results)
        else:
            # 4. Recommendations tier: 0.40–0.64 similarity band.
            results = await _execute_hybrid_vector_query(
                query_vec=query_vec,
                latitude=request.latitude,
                longitude=request.longitude,
                market_id=request.market_id,
                db=db,
                min_similarity=0.40,
                max_similarity=0.64,
                filters=request.filters,
                lexical_query_normalized=normalized_query,
            )
            if results:
                results = await _rerank_candidates(request.query_text, results)
                results = _filter_top_five_unless_accuracy_above_80(results)
                search_mode = "recommendations"
                action = "recommendations"
                found = True
            else:
                found = False
                action = "request_more_details"

                # 5. Cache SearchAlert — dedup on (user_id, query_text)
                existing_alert_stmt = select(SearchAlert).where(
                    SearchAlert.user_id == user.id,
                    func.lower(SearchAlert.query_text) == request.query_text.lower().strip(),
                )
                existing_alert = (await db.execute(existing_alert_stmt)).scalar_one_or_none()
                if not existing_alert:
                    alert = SearchAlert(
                        user_id=user.id,
                        query_text=request.query_text,
                        query_vector=query_vec,
                        latitude=request.latitude,
                        longitude=request.longitude,
                        is_active=True,
                    )
                    db.add(alert)
                    await db.flush()
                    logger.info(
                        f"[SEARCH ALERT ENGINE] Cached alert for user={user.id} "
                        f"term='{request.query_text}'"
                    )

        return HybridSearchResponse(
            found=found,
            action=action,
            search_mode=search_mode,
            results=results,
        )

    except Exception as e:
        logger.error(f"Hybrid search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during search execution.",
        )


# ── POST /image — DISABLED in text-only phase ──────────────────
@router.post("/image", response_model=HybridSearchResponse)
async def image_search(
    image: UploadFile = File(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    market_id: Optional[uuid.UUID] = Form(None),
    limit: int = Form(15),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Visual product search — disabled in the current text-only phase.
    Returns 410 Gone. Re-enable by setting settings.enable_image_search=True
    and re-introducing the Gemma-VLM → CLIP pipeline.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Image search is temporarily disabled. Enable settings.enable_image_search to restore.",
    )


# ── POST /double-check ──────────────────────────────────────────
@router.post("/double-check", response_model=HybridSearchResponse)
async def double_check_search(
    request: DoubleCheckSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Secondary fallback: concat original query + user-supplied details,
    re-embed with Qwen3, re-rerank.
    """
    try:
        refined_query = f"{request.original_query_text.strip()} {request.user_refined_details.strip()}"
        normalized_refined = normalize_query(refined_query)

        query_vec = (await embedding_service.encode_text_async(
            normalized_refined or refined_query
        )).tolist()

        results = await _execute_hybrid_vector_query(
            query_vec=query_vec,
            latitude=request.latitude,
            longitude=request.longitude,
            market_id=request.market_id,
            db=db,
            lexical_query_normalized=normalized_refined,
        )

        if results:
            results = await _rerank_candidates(refined_query, results)
        results = _filter_top_five_unless_accuracy_above_80(results)

        return HybridSearchResponse(
            found=len(results) > 0,
            action=None if results else "zero_results",
            search_mode="exact_matches",
            results=results,
        )

    except Exception as e:
        logger.error(f"Fallback double-check search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during refined search execution.",
        )