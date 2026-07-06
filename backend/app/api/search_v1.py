"""
Search V1 API — RRF hybrid retrieval + LLM multi-query expansion
+ always-on Qwen3 cross-encoder reranking + language-aware ordering.

Quality-first / latency-tolerant / serverless-cost-optimized pipeline:

  1. Normalize the query (Arabic NFKC + alef/hamza unification + Arabizi → Arabic).
  2. Expand the query with a small DeepInfra-hosted LLM into up to N variants
     (English translation, Arabic synonym, category phrase). Failures degrade
     silently to the original query only.
  3. Embed original + variants via Qwen3-Embedding-0.6B (cache-first, 1024-d).
  4. Ranked retrieval branches in Postgres (top-K each):
       - one semantic branch per query vector  (pgvector cosine over HNSW)
       - one lexical branch                    (arabic+simple tsvector, ts_rank, GIN)
  5. Reciprocal Rank Fusion (k = settings.rrf_k) across all branches.
  6. Qwen3-Reranker cross-encoder over the fused top-K (always on).
       relevance = w·rerank + (1-w)·prior
       prior     = 0.7·semantic + 0.3·proximity   (global)
                 = 1.0·semantic                   (in-shop)
  7. Language-aware ordering: identical result SET for شاي / \"tea\", with a
     small tie-break boost for items whose name script matches the query script.
  8. Single-pass tiering on the fused relevance score:
       exact (≥ exact_tier_threshold) → recommendations
       (≥ recommendation_tier_threshold) → SearchAlert cache.
  9. Top-5 cap unless ≥5 results score ≥ 0.80.

Image search endpoint (/image) remains hidden — returns 410 Gone until
settings.enable_image_search is flipped on.
"""

import asyncio
import math as _m
import re
import uuid
import logging
from collections import defaultdict
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, File, Form, UploadFile
from geoalchemy2.elements import WKTElement
from geoalchemy2 import Geometry, Geography
from sqlalchemy import select, func, literal
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
from app.services.query_expansion import query_expansion_service
from app.services.arabic_norm import normalize_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/search", tags=["Search V1"])

_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def _script_of(text: str | None) -> str:
    """Classify a string as Arabic-script ('ar') or Latin-script ('latin')."""
    return "ar" if text and _ARABIC_RE.search(text) else "latin"


def _safe(v, default: float = 0.0) -> float:
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return default
    if _m.isnan(fv) or _m.isinf(fv):
        return default
    return fv


# ── Retrieval: ranked branches + Reciprocal Rank Fusion ────────────
async def _retrieve_fused_candidates(
    db: AsyncSession,
    query_vecs: List[List[float]],
    lexical_variants: List[str],
    latitude: float,
    longitude: float,
    market_id: Optional[uuid.UUID],
    filters: Optional[SearchFilters],
) -> List[dict]:
    """
    Run one ranked semantic branch per query vector plus one ranked lexical
    branch, then fuse with Reciprocal Rank Fusion. Returns fused candidates
    (dicts with 'result' item + 'text' for the reranker), best-first, capped
    at settings.reranker_top_k.
    """
    point_wkt = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
    geog_location = Market.location.cast(Geography)
    geog_point = func.cast(point_wkt, Geography)
    distance_km_expr = (func.ST_Distance(geog_location, geog_point) / 1000.0)

    max_dist_km = settings.default_search_radius_km
    if filters and filters.max_distance_km is not None and filters.max_distance_km > 0:
        max_dist_km = filters.max_distance_km
    radius_meters = max_dist_km * 1000.0

    proximity_score_expr = func.greatest(0.0, 1.0 - (distance_km_expr / max_dist_km))

    # Semantic score vs the ORIGINAL query vector rides along on every branch
    # so lexical-only hits still carry a real semantic prior for the reranker.
    primary_vec = query_vecs[0] if query_vecs else None
    if primary_vec is not None:
        semantic_score_expr = func.coalesce(
            1.0 - GlobalItem.text_embedding.cosine_distance(primary_vec), 0.0
        )
    else:
        semantic_score_expr = literal(0.0)

    def _base_stmt():
        stmt = (
            select(
                MarketItem,
                GlobalItem,
                Market,
                func.ST_Y(Market.location.cast(Geometry)).label("lat"),
                func.ST_X(Market.location.cast(Geometry)).label("lng"),
                distance_km_expr.label("distance_km"),
                semantic_score_expr.label("semantic_score"),
                proximity_score_expr.label("proximity_score"),
            )
            .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
            .join(Market, MarketItem.market_id == Market.id)
            .options(
                selectinload(GlobalItem.category_rel),
                selectinload(GlobalItem.images),
            )
        )

        if filters and filters.in_stock_only:
            stmt = stmt.where(MarketItem.status == True, MarketItem.stock_count > 0)
        else:
            stmt = stmt.where(MarketItem.status == True)

        if filters:
            if filters.business_nature:
                stmt = stmt.where(
                    Market.business_nature.ilike(f"%{filters.business_nature}%")
                )
            if filters.category_id:
                stmt = stmt.where(GlobalItem.category_id == filters.category_id)
            if filters.price_min is not None:
                stmt = stmt.where(MarketItem.price >= filters.price_min)
            if filters.price_max is not None:
                stmt = stmt.where(MarketItem.price <= filters.price_max)
            if filters.city:
                # Normalize both sides: collapse punctuation/whitespace into a
                # single wildcard so \"As Salt\" / \"As-Salt\" / \"As_Salt\" match.
                city_token = re.sub(r"[\s\-_]+", "%", filters.city.strip().lower())
                stmt = stmt.where(
                    func.lower(Market.address).op("LIKE")(f"%{city_token}%")
                )

        if market_id:
            stmt = stmt.where(MarketItem.market_id == market_id)
        else:
            stmt = stmt.where(func.ST_DWithin(geog_location, geog_point, radius_meters))
        return stmt

    ranked_lists: List[List[uuid.UUID]] = []
    rows_by_key: dict = {}

    async def _run_branch(stmt) -> None:
        result = await db.execute(stmt)
        rows = result.unique().all()
        keys: List[uuid.UUID] = []
        for row in rows:
            key = row[0].id  # MarketItem.id — unique per (item, market) pair
            rows_by_key.setdefault(key, row)
            keys.append(key)
        ranked_lists.append(keys)

    # Semantic branches — one per query vector (original + LLM variants).
    for vec in query_vecs:
        stmt = (
            _base_stmt()
            .where(GlobalItem.text_embedding.is_not(None))
            .order_by(GlobalItem.text_embedding.cosine_distance(vec).asc())
            .limit(settings.retrieval_per_branch)
        )
        await _run_branch(stmt)

    # Lexical branch — one OR-combined tsquery across all query variants.
    tsq = None
    for v in lexical_variants:
        if not v or not v.strip():
            continue
        part = func.plainto_tsquery("arabic", v).op("||")(
            func.plainto_tsquery("simple", v)
        )
        tsq = part if tsq is None else tsq.op("||")(part)
    if tsq is not None:
        stmt = (
            _base_stmt()
            .where(GlobalItem.search_tsv.op("@@")(tsq))
            .order_by(func.ts_rank(GlobalItem.search_tsv, tsq).desc())
            .limit(settings.retrieval_per_branch)
        )
        await _run_branch(stmt)

    # Reciprocal Rank Fusion across all ranked lists.
    rrf_scores: dict = defaultdict(float)
    for keys in ranked_lists:
        for rank, key in enumerate(keys):
            rrf_scores[key] += 1.0 / (settings.rrf_k + rank + 1)

    fused_keys = sorted(rrf_scores, key=rrf_scores.get, reverse=True)
    fused_keys = fused_keys[: settings.reranker_top_k]

    # Opportunistic market-schedule refresh for the fused set.
    unique_markets = list(
        {rows_by_key[k][2].id: rows_by_key[k][2] for k in fused_keys}.values()
    )
    if unique_markets:
        from app.utils.schedule import check_and_update_markets_schedule
        try:
            await check_and_update_markets_schedule(db, unique_markets)
        except Exception as e:
            logger.warning(f"Schedule refresh skipped: {e}")

    fused: List[dict] = []
    for key in fused_keys:
        mi, gi, market, lat, lng, dist_km, sem_score, prox_score = rows_by_key[key]
        sem = _safe(sem_score)
        prox = _safe(prox_score)
        prior = sem if market_id else (0.7 * sem) + (0.3 * prox)
        price_val = float(mi.price) if getattr(mi, "price", None) is not None else None

        item = HybridSearchResultItem(
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
            semantic_score=round(sem, 4),
            proximity_score=round(prox, 4),
            final_score=round(prior, 4),
        )

        # Rich document for the cross-encoder: search_terms carries brand
        # aliases and cross-lingual synonyms, category anchors intent.
        text_parts = [gi.name]
        if gi.description:
            text_parts.append(gi.description)
        if gi.search_terms:
            text_parts.append(gi.search_terms)
        if gi.category:
            text_parts.append(gi.category)

        fused.append({"result": item, "text": " ".join(text_parts)})
    return fused


# ── Rerank + language-aware final ordering ─────────────────────────
async def _rerank_and_finalize(
    query_text: str,
    fused: List[dict],
    query_script: str,
) -> List[HybridSearchResultItem]:
    """
    Cross-encode the fused candidates (always on), fuse
    final = w·rerank + (1-w)·prior, then apply the language tie-break boost
    and sort. On reranker failure the RRF/prior ordering is preserved.
    """
    if not fused:
        return []

    out: List[HybridSearchResultItem] = []
    if settings.enable_reranker:
        candidates = [
            {
                "text": f["text"],
                "final_score": f["result"].final_score,
                "semantic_score": f["result"].semantic_score,
                "result": f["result"],
            }
            for f in fused
        ]
        reranked = await reranker_service.rerank_async(
            query=query_text,
            candidates=candidates,
            top_k=settings.reranker_final_k,
        )
        for c in reranked:
            r = c["result"]
            r.final_score = _safe(c.get("final_score", r.final_score))
            # Rerank score doubles as the accuracy proxy for the top-5 cap.
            r.semantic_score = _safe(c.get("rerank_score", r.semantic_score))
            out.append(r)
    else:
        out = [f["result"] for f in fused][: settings.reranker_final_k]

    # Language-aware ordering: same result SET across languages; items whose
    # name script matches the query script win ties.
    for r in out:
        if _script_of(r.name) == query_script:
            r.final_score = round(r.final_score + settings.language_match_boost, 4)
    out.sort(key=lambda r: r.final_score, reverse=True)
    return out


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


# ── Shared pipeline ────────────────────────────────────────────────
async def _run_search(
    query_text: str,
    latitude: float,
    longitude: float,
    market_id: Optional[uuid.UUID],
    filters: Optional[SearchFilters],
    db: AsyncSession,
) -> tuple[List[HybridSearchResultItem], List[float]]:
    """
    Full pipeline: normalize → expand → embed (multi-query) → RRF retrieval
    → rerank → language-aware ordering. Returns (scored results, primary
    query vector for SearchAlert caching).
    """
    normalized_query = normalize_query(query_text)
    query_script = _script_of(query_text)

    # 1. LLM multi-query expansion (graceful — never blocks search on failure).
    variants: List[str] = []
    if settings.enable_query_expansion:
        try:
            variants = await query_expansion_service.expand_async(query_text)
        except Exception as e:
            logger.warning(f"Query expansion skipped: {e}")

    texts: List[str] = [normalized_query or query_text]
    for v in variants:
        nv = normalize_query(v) or v.strip()
        if nv and nv not in texts:
            texts.append(nv)

    # 2. Embed original + variants in parallel (cache-first).
    embeddings = await asyncio.gather(
        *[embedding_service.encode_text_async(t) for t in texts]
    )
    primary_raw = embeddings[0].tolist()
    # Zero vectors (provider failure) are dropped — search degrades to the
    # remaining vectors, or to lexical-only ranking if none survive.
    query_vecs = [e.tolist() for e in embeddings if bool(e.any())]

    # 3. Ranked branches + RRF.
    fused = await _retrieve_fused_candidates(
        db=db,
        query_vecs=query_vecs,
        lexical_variants=texts,
        latitude=latitude,
        longitude=longitude,
        market_id=market_id,
        filters=filters,
    )

    # 4. Cross-encode + language-aware ordering.
    scored = await _rerank_and_finalize(query_text, fused, query_script)
    return scored, primary_raw


# ── POST /hybrid ────────────────────────────────────────────────
@router.post("/hybrid", response_model=HybridSearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hybrid text search: multi-query Qwen3 semantic + Arabic tsvector lexical,
    fused with RRF, refined by the Qwen3 reranker, ordered language-aware.
    Single-pass tiering: exact → recommendations → SearchAlert.
    """
    try:
        scored, primary_vec = await _run_search(
            query_text=request.query_text,
            latitude=request.latitude,
            longitude=request.longitude,
            market_id=request.market_id,
            filters=request.filters,
            db=db,
        )

        # Gate tiers on RELEVANCE (semantic_score = rerank sigmoid when the
        # reranker ran, raw cosine on fallback) — never on final_score.
        # final_score includes 0.3*proximity, which let nearby-but-irrelevant
        # items (e.g. tea for "كرسي مريح") pass the exact tier. Proximity
        # only influences ORDERING within a tier, not whether an item is shown.
        exact = [r for r in scored if r.semantic_score >= settings.exact_tier_threshold]
        if exact:
            return HybridSearchResponse(
                found=True,
                action=None,
                search_mode="exact_matches",
                results=_filter_top_five_unless_accuracy_above_80(exact),
            )

        recommendations = [
            r for r in scored
            if r.semantic_score >= settings.recommendation_tier_threshold
        ]
        if recommendations:
            return HybridSearchResponse(
                found=True,
                action="recommendations",
                search_mode="recommendations",
                results=_filter_top_five_unless_accuracy_above_80(recommendations),
            )

        # Nothing relevant — cache a SearchAlert (dedup on user_id + query_text).
        existing_alert_stmt = select(SearchAlert).where(
            SearchAlert.user_id == user.id,
            func.lower(SearchAlert.query_text) == request.query_text.lower().strip(),
        )
        existing_alert = (await db.execute(existing_alert_stmt)).scalar_one_or_none()
        if not existing_alert:
            alert = SearchAlert(
                user_id=user.id,
                query_text=request.query_text,
                query_vector=primary_vec,
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
            found=False,
            action="request_more_details",
            search_mode="exact_matches",
            results=[],
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
    Secondary fallback: concat original query + user-supplied details, then
    run the full expansion → RRF → rerank pipeline on the refined query.
    """
    try:
        refined_query = (
            f"{request.original_query_text.strip()} "
            f"{request.user_refined_details.strip()}"
        )

        scored, _ = await _run_search(
            query_text=refined_query,
            latitude=request.latitude,
            longitude=request.longitude,
            market_id=request.market_id,
            filters=None,
            db=db,
        )
        # Same relevance gate as /hybrid — never surface items below the
        # recommendation floor just because they were the least-bad candidates.
        scored = [
            r for r in scored
            if r.semantic_score >= settings.recommendation_tier_threshold
        ]
        results = _filter_top_five_unless_accuracy_above_80(scored)

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
