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

from fastapi import APIRouter, Depends, HTTPException, status, File, Form, UploadFile, Request
from app.rate_limit import limiter
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


# ── Gender exclusion filter (keyword-based) ────────────────────────
_FEMALE_KEYWORDS = {"نسائي", "نسائية", "نساء", "بنات", "حريم", "ستات", "women", "female", "ladies"}
_MALE_KEYWORDS = {"رجالي", "رجالية", "رجال", "اولاد", "شباب", "men", "male"}


def _get_gender_filter(query: str) -> str | None:
    """Returns 'female', 'male', or None based on query keywords."""
    query_words = set(query.lower().split())
    if query_words & _FEMALE_KEYWORDS:
        return "female"
    if query_words & _MALE_KEYWORDS:
        return "male"
    return None


def _is_gender_excluded(item_text: str, gender_filter: str) -> bool:
    """Returns True if this item should be excluded based on the opposite gender keywords."""
    item_words = set(item_text.lower().split())
    if gender_filter == "female":
        return bool(item_words & _MALE_KEYWORDS)
    if gender_filter == "male":
        return bool(item_words & _FEMALE_KEYWORDS)
    return False


# ── Retrieval: ranked branches + Reciprocal Rank Fusion ────────────
async def _retrieve_fused_candidates(
    db: AsyncSession,
    query_vecs: List[List[float]],
    lexical_variants: List[str],
    latitude: float,
    longitude: float,
    market_id: Optional[uuid.UUID],
    filters: Optional[SearchFilters],
    listing_type: Optional[str] = None,
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

        if listing_type:
            stmt = stmt.where(GlobalItem.listing_type == listing_type)

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
            listing_type=getattr(gi, "listing_type", "product") or "product",
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
        # De-duplicate terms/phrases to prevent artificial amplification of phonetic matches.
        raw_parts = []
        if gi.name:
            raw_parts.append(gi.name)
        if gi.description:
            raw_parts.append(gi.description)
        if gi.search_terms:
            raw_parts.append(gi.search_terms)
        if gi.category:
            raw_parts.append(gi.category)

        seen_chunks = set()
        deduped_parts = []
        for part in raw_parts:
            # Clean and split into distinct meaningful chunks/words
            cleaned = re.sub(r"\s+", " ", str(part)).strip()
            if not cleaned:
                continue
            cleaned_lower = cleaned.lower()
            if cleaned_lower not in seen_chunks:
                seen_chunks.add(cleaned_lower)
                deduped_parts.append(cleaned)

        doc_text = " - ".join(deduped_parts) if deduped_parts else (gi.name or "")
        fused.append({"result": item, "text": doc_text, "cosine_sim": sem})
    return fused


# ── Rerank + language-aware final ordering ─────────────────────────
async def _rerank_and_finalize(
    query_text: str,
    fused: List[dict],
    query_script: str,
) -> List[HybridSearchResultItem]:
    """
    Cross-encode the fused candidates (always on), then blend:
    semantic_score = final_score = 0.7 * rerank_score + 0.3 * cosine_sim.
    Applies the language tie-break boost and sorts by semantic_score.
    On reranker failure the RRF/prior ordering is preserved.
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
                "cosine_sim": f.get("cosine_sim", f["result"].semantic_score),
                "result": f["result"],
            }
            for f in fused
        ]
        reranked = await reranker_service.rerank_async(
            query=query_text,
            candidates=candidates,
            top_k=settings.reranker_final_k,
        )
        rerank_log_entries = []
        for c in reranked:
            r = c["result"]
            cosine_sim = _safe(c.get("cosine_sim", r.semantic_score))
            rerank_score = _safe(c.get("rerank_score", r.semantic_score))
            blended = round(0.7 * rerank_score + 0.3 * cosine_sim, 4)
            r.semantic_score = blended
            r.final_score = blended
            out.append(r)
            rerank_log_entries.append((r, cosine_sim, rerank_score, blended))

        # ── Diagnostic logging ──────────────────────────────────
        logger.debug(
            "[RANKING DEBUG] query=%r  candidates=%d  reranked=%d",
            query_text, len(candidates), len(reranked),
        )
        for i, (r, orig_cosine, rr_score, blnd) in enumerate(rerank_log_entries):
            logger.debug(
                "[RANKING DEBUG]  #%d  name=%r  rerank=%.4f  "
                "cosine_sim=%.4f  blended=%.4f  proximity=%.4f  distance_km=%.2f  "
                "final=%.4f",
                i + 1, r.name, rr_score,
                orig_cosine,
                blnd,
                _safe(r.proximity_score),
                _safe(r.distance_km),
                r.final_score,
            )
    else:
        out = [f["result"] for f in fused][: settings.reranker_final_k]

    # Sort results by blended relevance score (language match boost removed to support cross-lingual search)
    out.sort(key=lambda r: r.semantic_score, reverse=True)
    return out


def _filter_top_five_unless_accuracy_above_80(
    results: List[HybridSearchResultItem],
) -> List[HybridSearchResultItem]:
    """
    Legacy 0.80-gated top-5 cap. Kept as a thin shim over the new
    `_filter_with_guards` so legacy call sites keep working during the
    guard rollout. Defaults to lenient mode with empty query tokens.
    """
    return _filter_with_guards(results, query_text="", lenient=True)


def _filter_with_guards(
    results: List[HybridSearchResultItem],
    query_text: str = "",
    lenient: bool = True,
) -> List[HybridSearchResultItem]:
    """
    Three-stage post-rerank guard applied to the top-N candidates.

    Stage A — shelf behavior
        If ≥5 candidates score ≥ reranker_strong_confidence (0.70), return
        all candidates up to settings.reranker_final_k.

    Stage B — score-gap + token-overlap demote (lenient by default)
        For any candidate whose rerank-score gap to #1 is below
        `reranker_score_gap_threshold` (0.15) AND whose query/candidate
        token overlap is below `reranker_token_overlap_min` (1), demote
        to the end of the list AND keep it only if the strict list above
        it has fewer than `cap` items.

    Stage C — min-score floor
        Drop any candidate with score below `reranker_min_keep_score` (0.50).
    """
    if not results:
        logger.debug("[GUARD FILTER] query=%r  input_count=0  output_count=0", query_text)
        return []

    from app.services.query_filter import extract_query_tokens, tokens_overlap

    input_count = len(results)

    # Stable sort by semantic_score (blended relevance) desc
    sorted_results = sorted(results, key=lambda r: r.semantic_score, reverse=True)
    top_score = sorted_results[0].semantic_score if sorted_results else 0.0

    # Stage A — shelf behavior for high-confidence matches (lowered to 0.70 for blended scores)
    strong_threshold = getattr(settings, "reranker_strong_confidence", 0.70)
    strong = [r for r in sorted_results if r.semantic_score >= strong_threshold]
    if len(strong) >= 5:
        final_strong = strong[: settings.reranker_final_k]
        logger.debug(
            "[GUARD FILTER] query=%r  input_count=%d  output_count=%d  (strong_shelf_applied, threshold=%.2f)",
            query_text, input_count, len(final_strong), strong_threshold,
        )
        return final_strong

    # Extract query tokens once (cache for the loop)
    q_tokens = extract_query_tokens(query_text) if query_text else {
        "brands": set(), "sizes": set(), "category_terms": set()
    }

    kept: List[HybridSearchResultItem] = []
    demoted: List[HybridSearchResultItem] = []

    for r in sorted_results:
        # Stage C — absolute floor
        if r.semantic_score < settings.reranker_min_keep_score:
            continue

        # Stage B — gap + overlap demotion
        gap = top_score - r.semantic_score
        if gap < settings.reranker_score_gap_threshold:
            name_val = r.name if isinstance(r.name, str) else ""
            desc_val = r.description if isinstance(r.description, str) else ""
            doc_text = f"{name_val} {desc_val}".strip()
            overlap = tokens_overlap(q_tokens, doc_text) if q_tokens else 1
            if overlap < settings.reranker_token_overlap_min:
                demoted.append(r)
                continue

        kept.append(r)

    # Allow up to settings.reranker_final_k results
    cap = settings.reranker_final_k
    final = kept[:cap]
    # Lenient mode: backfill demoted items only if we have fewer than `cap` kept
    if lenient and len(final) < cap:
        for d in demoted:
            if len(final) >= cap:
                break
            final.append(d)

    logger.debug(
        "[GUARD FILTER] query=%r  input_count=%d  output_count=%d  (kept=%d, demoted_backfilled=%d, cap=%d)",
        query_text, input_count, len(final), len(kept), max(0, len(final) - len(kept)), cap,
    )

    # ── Gender exclusion: remove opposite-gender items ──────────
    gender_filter = _get_gender_filter(query_text)
    if gender_filter:
        before_gender = len(final)
        final = [
            r for r in final
            if not _is_gender_excluded(f"{r.name} {r.description or ''}", gender_filter)
        ]
        if len(final) < before_gender:
            logger.debug(
                "[GENDER FILTER] query=%r  filter=%s  before=%d  after=%d",
                query_text, gender_filter, before_gender, len(final),
            )

    # Ensure output is always strictly ordered by semantic_score descending
    final.sort(key=lambda r: r.semantic_score, reverse=True)
    return final


# ── Shared pipeline ────────────────────────────────────────────────
async def _run_search(
    query_text: str,
    latitude: float,
    longitude: float,
    market_id: Optional[uuid.UUID],
    filters: Optional[SearchFilters],
    db: AsyncSession,
    listing_type: Optional[str] = None,
) -> tuple[List[HybridSearchResultItem], List[float]]:
    """
    Full pipeline: normalize → expand → embed (multi-query) → RRF retrieval
    → rerank → language-aware ordering. Returns (scored results, primary
    query vector for SearchAlert caching).
    """
    from app.services.query_understanding import query_understanding_service

    effective_listing_type = listing_type
    if not effective_listing_type:
        try:
            intent_analysis = await query_understanding_service.analyze_query_async(query_text)
            if intent_analysis.intent in ("product", "service"):
                effective_listing_type = intent_analysis.intent
        except Exception as e:
            logger.warning(f"Query understanding skipped: {e}")

    normalized_query = normalize_query(query_text)
    query_script = _script_of(query_text)

    # 1. LLM multi-query expansion (graceful — never blocks search on failure).
    variants: List[str] = []
    if settings.enable_query_expansion:
        try:
            variants = await query_expansion_service.expand_async(query_text)
            logger.debug(
                "[EXPANSION DEBUG] original_query=%r  expansion_variants=%s",
                query_text, variants,
            )
        except Exception as e:
            logger.warning(f"Query expansion skipped: {e}")

    from app.services.arabic_norm import arabizi_to_arabic

    texts: List[str] = [normalized_query or query_text]
    arabicized = arabizi_to_arabic(query_text)
    if arabicized and arabicized.strip() and arabicized.lower() != query_text.lower():
        norm_arabicized = normalize_query(arabicized)
        if norm_arabicized and norm_arabicized not in texts:
            texts.append(norm_arabicized)

    for v in variants:
        nv = normalize_query(v) or v.strip()
        if nv and nv not in texts:
            texts.append(nv)

    logger.debug(
        "[SEARCH BRANCHES] query=%r  all_text_branches=%s",
        query_text, texts,
    )

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
        listing_type=effective_listing_type,
    )

    # Choose the most canonical search term for cross-encoder reranking:
    # if the query was Arabizi (e.g. "7aleeb"), pass the transliterated Arabic ("حليب")
    # so the cross-encoder compares semantic concepts rather than raw Franco-Arabic chars.
    rerank_query = norm_arabicized if (arabicized and arabicized.strip() and arabicized.lower() != query_text.lower() and norm_arabicized) else (normalized_query or query_text)

    # 4. Cross-encode + language-aware ordering.
    scored = await _rerank_and_finalize(rerank_query, fused, query_script)
    return scored, primary_raw


# ── POST /hybrid ────────────────────────────────────────────────
@router.post("/hybrid", response_model=HybridSearchResponse)
@limiter.limit("30/minute")
async def hybrid_search(
    request: Request,
    search_request: HybridSearchRequest,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hybrid text search: multi-query Qwen3 semantic + Arabic tsvector lexical,
    fused with RRF, refined by the Qwen3 reranker, ordered language-aware.
    Single-pass tiering: exact → recommendations → SearchAlert.
    """
    try:
        scored, primary_vec = await _run_search(
            query_text=search_request.query_text,
            latitude=search_request.latitude,
            longitude=search_request.longitude,
            market_id=search_request.market_id,
            filters=search_request.filters,
            listing_type=search_request.listing_type,
            db=db,
        )

        # Gate tiers on RELEVANCE (semantic_score = rerank sigmoid when the
        # reranker ran, raw cosine on fallback) — never on final_score.
        # final_score includes 0.3*proximity, which let nearby-but-irrelevant
        # items (e.g. tea for "كرسي مريح") pass the exact tier. Proximity
        # only influences ORDERING within a tier, not whether an item is shown.
        exact = [r for r in scored if r.semantic_score >= settings.exact_tier_threshold]
        logger.debug(
            "[HYBRID SEARCH] query=%r  total_scored=%d  exact_tier_count=%d (threshold=%.2f)",
            search_request.query_text, len(scored), len(exact), settings.exact_tier_threshold,
        )

        if len(exact) >= 3:
            guarded_exact = _filter_with_guards(exact, query_text=search_request.query_text)
            logger.debug(
                "[HYBRID SEARCH RETURN] query=%r  exact_returning=%d",
                search_request.query_text, len(guarded_exact),
            )
            return HybridSearchResponse(
                found=True,
                action=None,
                search_mode="exact_matches",
                results=guarded_exact,
            )
        else:
            # Not enough exact matches (< 3) — include recommendation tier items as well
            recommendations = [
                r for r in scored
                if r.semantic_score >= settings.recommendation_tier_threshold
            ]
            logger.debug(
                "[HYBRID SEARCH] query=%r  recommendations_tier_count=%d (threshold=%.2f)",
                search_request.query_text, len(recommendations), settings.recommendation_tier_threshold,
            )
            if recommendations:
                guarded_recs = _filter_with_guards(recommendations, query_text=search_request.query_text)
                return HybridSearchResponse(
                    found=True,
                    action=None if exact else "recommendations",
                    search_mode="exact_matches" if exact else "recommendations",
                    results=guarded_recs,
                )
            elif exact:
                guarded_exact = _filter_with_guards(exact, query_text=search_request.query_text)
                return HybridSearchResponse(
                    found=True,
                    action=None,
                    search_mode="exact_matches",
                    results=guarded_exact,
                )

        # Nothing relevant — cache a SearchAlert (dedup on user_id + query_text).
        if user:
            existing_alert_stmt = select(SearchAlert).where(
                SearchAlert.user_id == user.id,
                func.lower(SearchAlert.query_text) == search_request.query_text.lower().strip(),
            )
            existing_alert = (await db.execute(existing_alert_stmt)).scalar_one_or_none()
            if not existing_alert:
                alert = SearchAlert(
                    user_id=user.id,
                    query_text=search_request.query_text,
                    query_vector=primary_vec,
                    latitude=search_request.latitude,
                    longitude=search_request.longitude,
                    is_active=True,
                )
                db.add(alert)
                await db.flush()
                logger.info(
                    f"[SEARCH ALERT ENGINE] Cached alert for user={user.id} "
                    f"term='{search_request.query_text}'"
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
@limiter.limit("30/minute")
async def double_check_search(
    request: Request,
    search_request: DoubleCheckSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Secondary fallback: concat original query + user-supplied details, then
    run the full expansion → RRF → rerank pipeline on the refined query.
    """
    try:
        refined_query = (
            f"{search_request.original_query_text.strip()} "
            f"{search_request.user_refined_details.strip()}"
        )

        scored, _ = await _run_search(
            query_text=refined_query,
            latitude=search_request.latitude,
            longitude=search_request.longitude,
            market_id=search_request.market_id,
            filters=None,
            db=db,
        )
        # Same relevance gate as /hybrid — never surface items below the
        # recommendation floor just because they were the least-bad candidates.
        scored = [
            r for r in scored
            if r.semantic_score >= settings.recommendation_tier_threshold
        ]
        results = _filter_with_guards(scored, query_text=refined_query)

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
