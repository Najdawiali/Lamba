"""Search V1 API — RRF hybrid retrieval + LLM multi-query expansion
+ always-on Qwen3 cross-encoder reranking + language-aware ordering.

LLM Prompt Architecture
=======================
9 prompts across the pipeline, each with a specific role:

REAL-TIME (per query, Qwen3.6-35B-A3B via DeepInfra):
  1. Query Understanding (_QU_SYSTEM_PROMPT in query_understanding.py)
     - Fires when needs_llm() returns True
     - Extracts: intent, query_clean, structured attributes
     - Attributes become hard JSONB filters (type, color, dietary, brand)
     - Occasions (فطور, هدية) are NOT attributes — stay in query_clean

  2. Query Expansion (EXPANSION_SYSTEM_PROMPT in query_expansion.py)
     - Fires when needs_expansion() returns True (currently DISABLED)
     - Input: primary_text (query_clean, NOT raw query) to avoid
       conflicting with attribute filters
     - Output: list of cross-lingual variant strings

OFFLINE (batch scripts, Gemma 4 31B via DeepInfra):
  3. Search Term Enrichment (ENRICHMENT_PROMPT in enrich_search_terms.py)
     - Generates dialect, Arabizi, English search terms per product
  4. Attribute Extraction (ATTRIBUTE_EXTRACTION_PROMPT in extract_product_attributes.py)
     - Extracts structured JSONB attributes per product
  5. Category Classification (inline in merchant_v1.py _classify_category)
     - Classifies new products into OFFICIAL_CATEGORIES

INFRASTRUCTURE (non-generative models):
  6. Embedding Instruction (config.embedding_query_instruction)
     - Steers asymmetric query embedding for Qwen3-Embedding
  7. Reranker Instruction (config.reranker_instruction)
     - Guides Qwen3-Reranker cross-encoder scoring (currently DISABLED)

Pipeline Steps
==============
  1. Normalize (Arabic NFKC + alef/hamza + Arabizi → Arabic).
  2. Synonym table lookup (O(1) Redis).
  3. Query Understanding → query_clean + attribute filters.
  4. Query Expansion (parallel with embedding) → cross-lingual variants.
  5. Embed original + variants via Qwen3-Embedding (cache-first, 1024-d).
  6. Ranked retrieval in Postgres (pgvector cosine + tsvector lexical).
  7. Reciprocal Rank Fusion (k = settings.rrf_k) across all branches.
  8. Qwen3-Reranker cross-encoder over fused top-K.
  9. Language-aware ordering + score tiering + top-K cap.

Image search endpoint (/image) remains hidden — returns 410 Gone until
settings.enable_image_search is flipped on.
"""

import asyncio
import time
import math as _m
import re
import uuid
import logging
from collections import defaultdict
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, File, Form, UploadFile, Request
from app.rate_limit import limiter
from geoalchemy2.elements import WKTElement
from geoalchemy2 import Geometry, Geography
from sqlalchemy import select, func, literal, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.api.auth import get_optional_current_user
from app.models.market import Market
from app.models.global_item import GlobalItem
from app.models.market_item import MarketItem
from app.models.category import Category
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
from app.services.attribute_filters import build_attribute_clauses
from app.services.attribute_rules import plan_attribute_filters
from app.services.cache import get_cached_search, cache_search, lookup_synonym

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


# ── Gender filter: now handled via attribute extraction in query
# understanding + JSONB filtering in _retrieve_fused_candidates ──────


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
    extracted_attrs: Optional[Dict[str, Any]] = None,
    category_id: Optional[uuid.UUID] = None,
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

    attr_plans = plan_attribute_filters(extracted_attrs)

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
            .where(GlobalItem.moderation_status == "approved")
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
                cat_ids_subquery = select(Category.id).where(
                    or_(
                        Category.id == filters.category_id,
                        Category.parent_category_id == filters.category_id,
                    )
                )
                stmt = stmt.where(GlobalItem.category_id.in_(cat_ids_subquery))
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

        # ── Attribute filters — rules in attribute_rules, SQL in attribute_filters ──
        if attr_plans:
            stmt = stmt.where(*build_attribute_clauses(
                attr_plans,
                attributes=GlobalItem.attributes,
                name=GlobalItem.name,
                name_ar=GlobalItem.name_ar,
                search_terms=GlobalItem.search_terms,
            ))

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

    # Category branch — items in the detected category (+ subcategories),
    # ranked by semantic similarity.  Gives category-matching items an extra
    # RRF vote so they rank higher even when their lexical/semantic scores
    # are moderate.
    if category_id:
        cat_ids_subq = select(Category.id).where(
            or_(
                Category.id == category_id,
                Category.parent_category_id == category_id,
            )
        )
        cat_stmt = (
            _base_stmt()
            .where(GlobalItem.category_id.in_(cat_ids_subq))
        )
        if primary_vec is not None:
            cat_stmt = (
                cat_stmt
                .where(GlobalItem.text_embedding.is_not(None))
                .order_by(GlobalItem.text_embedding.cosine_distance(primary_vec).asc())
            )
        cat_stmt = cat_stmt.limit(settings.retrieval_per_branch)
        await _run_branch(cat_stmt)

    # Reciprocal Rank Fusion across all ranked lists.
    rrf_scores: dict = defaultdict(float)
    for keys in ranked_lists:
        for rank, key in enumerate(keys):
            rrf_scores[key] += 1.0 / (settings.rrf_k + rank + 1)

    fused_keys = sorted(rrf_scores, key=rrf_scores.get, reverse=True)
    # Deduplicate fused_keys by product (gi.id) to collect the highest-ranked store per unique product
    unique_fused_keys = []
    seen_gi_ids = set()
    for key in fused_keys:
        gi_id = rows_by_key[key][1].id
        if gi_id not in seen_gi_ids:
            seen_gi_ids.add(gi_id)
            unique_fused_keys.append(key)
            if len(unique_fused_keys) >= 50:
                break

    # Opportunistic market-schedule refresh for the fused set.
    unique_markets = list(
        {rows_by_key[k][2].id: rows_by_key[k][2] for k in unique_fused_keys}.values()
    )
    if unique_markets:
        from app.utils.schedule import check_and_update_markets_schedule
        try:
            await check_and_update_markets_schedule(db, unique_markets)
        except Exception as e:
            logger.warning(f"Schedule refresh skipped: {e}")

    fused: List[dict] = []
    for key in unique_fused_keys:
        mi, gi, market, lat, lng, dist_km, sem_score, prox_score = rows_by_key[key]
        sem = _safe(sem_score)
        prox = _safe(prox_score)
        prior = sem if market_id else (0.7 * sem) + (0.3 * prox)
        price_val = float(mi.price) if getattr(mi, "price", None) is not None else None

        cat_rel = getattr(gi, "category_rel", None)
        cat_name = cat_rel.name if cat_rel else gi.category
        cat_name_ar = cat_rel.name_ar if cat_rel else None
        cat_name_en = cat_rel.name_en if cat_rel else None

        item = HybridSearchResultItem(
            item_id=gi.id,
            market_item_id=mi.id,
            name=gi.name,
            name_ar=getattr(gi, "name_ar", None),
            name_en=getattr(gi, "name_en", None),
            description=gi.description,
            category=cat_name,
            category_name_ar=cat_name_ar,
            category_name_en=cat_name_en,
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
        fused.append({
            "result": item,
            "text": doc_text,
            "cosine_sim": sem,
            "rrf_score": rrf_scores.get(key, 0.0),
            "category": cat_name,
            "category_name_ar": cat_name_ar,
            "category_name_en": cat_name_en,
        })
    return fused


# ── Rerank + language-aware final ordering ─────────────────────────
async def _rerank_and_finalize(
    query_text: str,
    fused: List[dict],
    query_script: str,
    skip_score_gap: bool = False,
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
            if len(out) < 5:
                logger.info(f"[BLEND] {r.name[:30]:30s} cosine={cosine_sim:.4f} rerank={rerank_score:.4f} blended={blended:.4f}")
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

    # Sort results by blended relevance score
    out.sort(key=lambda r: r.semantic_score, reverse=True)

    # ── Score-gap filter: remove results after a significant relevance drop ──
    # Standard IR technique: if there's a >15% relative drop between consecutive
    # results, the items below the gap are likely irrelevant.
    # Skipped for intent queries where diverse results at different score levels
    # are all valid (e.g. mansaf ingredients: bread, rice, yogurt).
    if not skip_score_gap and len(out) >= 2 and out[0].semantic_score > 0.5:
        filtered = [out[0]]
        for i in range(1, len(out)):
            prev_score = out[i - 1].semantic_score
            curr_score = out[i].semantic_score
            # Relative drop from previous item
            if prev_score > 0:
                relative_drop = (prev_score - curr_score) / prev_score
                if relative_drop > 0.15:
                    # Found a significant gap — stop here
                    logger.info(
                        f"[SCORE GAP] Cutting after #{i}: "
                        f"{out[i-1].name[:25]} ({prev_score:.3f}) → "
                        f"{out[i].name[:25]} ({curr_score:.3f}), "
                        f"drop={relative_drop:.1%}"
                    )
                    break
            filtered.append(out[i])
        out = filtered

    return _deduplicate_by_product(out)


def _is_valid_query(query: str) -> bool:
    """
    A valid query must contain at least one:
    - Arabic character (\\u0600-\\u06FF)
    - English letter (a-zA-Z)
    - Digit used as Arabizi / query term
    - Emoji (\\U0001F300-\\U0001FAFF)
    
    Pure punctuation, whitespace, symbols, or dots only are invalid.
    """
    stripped = query.strip() if query else ""
    if not stripped or len(stripped) < 1:
        return False
    has_arabic = bool(re.search(r"[\u0600-\u06FF]", stripped))
    has_latin = bool(re.search(r"[a-zA-Z]", stripped))
    has_emoji = bool(re.search(r"[\U0001F300-\U0001FAFF]", stripped))
    has_digit = bool(re.search(r"\d", stripped))
    if not has_arabic and not has_latin and not has_emoji and not has_digit:
        return False
    cleaned_chars = re.sub(r"[^\w\s\U0001F300-\U0001FAFF]", "", stripped)
    if not cleaned_chars.strip():
        return False
    return True


def _deduplicate_by_product(results: List[HybridSearchResultItem]) -> List[HybridSearchResultItem]:
    """
    Keep one result per global_item_id (item_id).
    When the same product appears from multiple stores,
    keep the one with the highest score.
    Preserve the original sort order.
    """
    seen_global_ids = set()
    deduplicated = []
    
    for r in results:
        global_id = getattr(r, "item_id", None) or getattr(r, "global_item_id", None)
        if global_id is None:
            deduplicated.append(r)
            continue
        if global_id not in seen_global_ids:
            seen_global_ids.add(global_id)
            deduplicated.append(r)
        # else: skip — a higher-scored version of this product is already in the list
    
    return deduplicated


def _dedup_candidates(candidates: list, max_unique: int = 50) -> list:
    """Keep one candidate per global_item_id (nearest/highest-ranked store), limit to max_unique products."""
    seen_ids = set()
    unique = []
    for c in candidates:
        r = c.get("result") if isinstance(c, dict) else None
        item_id = (
            getattr(r, "item_id", None)
            if r is not None
            else (c.get("item_id") or c.get("global_item_id") if isinstance(c, dict) else None)
        )
        if item_id and item_id in seen_ids:
            continue
        if item_id:
            seen_ids.add(item_id)
        unique.append(c)
        if len(unique) >= max_unique:
            break
    return unique


def _filter_with_guards(
    results: List[HybridSearchResultItem],
    query_text: str = "",
    lenient: bool = True,
    min_score_override: Optional[float] = None,
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
        final_strong = _deduplicate_by_product(strong)[: settings.reranker_final_k]
        final_strong.sort(key=lambda r: r.semantic_score, reverse=True)
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
        effective_min = min_score_override if min_score_override is not None else settings.reranker_min_keep_score
        if r.semantic_score < effective_min:
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

    # Gender exclusion is now handled by attribute-based JSONB filtering
    # in _retrieve_fused_candidates (extracted from query understanding).

    # ── De-duplicate identical products across stores ──────────
    before_count = len(final)
    final = _deduplicate_by_product(final)
    # Ensure output is always strictly ordered by semantic_score descending
    final.sort(key=lambda r: r.semantic_score, reverse=True)
    logger.debug(
        "[DEDUP] query=%r Before: %d, After: %d, Removed: %d duplicates",
        query_text, before_count, len(final), before_count - len(final)
    )
    return final


def needs_expansion(query: str, script: str = "ar", has_synonym: bool = False) -> bool:
    """Skip expansion for simple product queries — catalog enrichment covers dialects and synonyms."""
    if not query or not query.strip():
        return False

    words = query.strip().lower().split()

    # Synonym table already provided the formal term — skip LLM
    if has_synonym and len(words) <= 2:
        return False

    q_lower = query.strip().lower()

    # Intent markers — these need expansion to generate product terms
    intent_markers = {
        "بدي", "ابغى", "اريد", "وين", "فين", "شي", "أغراض", "اغراض",
        "هدية", "أحسن", "احسن", "أفضل", "افضل", "أرخص", "ارخص", "بديل", "للفطور", "للعشاء", "للغداء"
    }
    if any(m in q_lower for m in intent_markers):
        return True

    # Single word queries that are known product names don't need expansion.
    # Category-level terms ("اكل", "مطبخ", "حلويات") DO need expansion
    # to generate concrete searchable product terms.
    if len(words) <= 1:
        from app.services.query_understanding import _SIMPLE_PRODUCT_TERMS, _CATEGORY_TERMS
        if q_lower in _CATEGORY_TERMS:
            return True
        return False

    # Two-word queries that look like product names (Arabic script) — skip expansion
    if len(words) == 2 and (script in ("ar", "arabic") or bool(_ARABIC_RE.search(query))):
        return False

    # 3+ words — complex query
    if len(words) >= 3:
        return True

    # Arabizi / latin queries — expansion helps translate to Arabic
    if script in ("latin", "arabizi"):
        return True

    return False


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
    t0 = time.time()

    if not _is_valid_query(query_text):
        logger.debug("[SEARCH VALIDATION] Query %r is invalid (pure punctuation/empty/symbols only)", query_text)
        return [], []

    # 1. Normalization & Arabizi transliteration
    from app.services.arabic_norm import arabizi_to_arabic
    normalized_input = normalize_query(query_text)
    arabicized = arabizi_to_arabic(query_text)
    norm_arabicized = normalize_query(arabicized) if arabicized else None

    # Base text to resolve synonyms against (use Arabizi translation if Latin/Arabizi)
    base_text = norm_arabicized if (norm_arabicized and norm_arabicized != normalized_input) else (normalized_input or query_text)

    # 2. Synonym expansion from pre-built table (<1ms O(1) Redis lookup)
    # Resolve dialect words to formal Arabic BEFORE query understanding
    words = base_text.split()
    resolved_query = base_text
    synonym_variants: List[str] = []

    for word in words:
        synonym = await lookup_synonym(word)
        if synonym and synonym != word:
            resolved_query = resolved_query.replace(word, synonym)
            if resolved_query not in synonym_variants and resolved_query != base_text:
                synonym_variants.append(resolved_query)
            if len(words) == 1 and synonym not in synonym_variants and synonym != base_text:
                synonym_variants.append(synonym)

    # 3. Query Understanding on resolved query
    from app.services.query_understanding import query_understanding_service
    effective_listing_type = listing_type
    extracted_attrs: Dict[str, Any] = {}
    query_clean: Optional[str] = None
    intent_analysis = None
    try:
        intent_analysis = await query_understanding_service.analyze_query_async(resolved_query)
        if not effective_listing_type and intent_analysis.intent in ("product", "service"):
            effective_listing_type = intent_analysis.intent
        extracted_attrs = intent_analysis.attributes or {}
        query_clean = intent_analysis.query_clean
        if extracted_attrs:
            logger.info(f"[ATTR FILTER] query={query_text!r} resolved={resolved_query!r} attrs={extracted_attrs} query_clean={query_clean!r}")
    except Exception as e:
        logger.warning(f"Query understanding skipped: {e}")

    # ── Resolve category for retrieval branch ────────────────────
    resolved_category_id: Optional[uuid.UUID] = None
    if intent_analysis and getattr(intent_analysis, 'category_name', None):
        _cat_name = intent_analysis.category_name.strip()
        if _cat_name:
            # Exact match (case-insensitive) on name / name_ar / name_en
            _cat_row = (await db.execute(
                select(Category.id).where(
                    or_(
                        func.lower(Category.name) == _cat_name.lower(),
                        func.lower(Category.name_ar) == _cat_name.lower(),
                        func.lower(Category.name_en) == _cat_name.lower(),
                    )
                ).limit(1)
            )).first()
            if not _cat_row:
                # Fuzzy fallback — ILIKE substring
                _cat_row = (await db.execute(
                    select(Category.id).where(
                        or_(
                            Category.name.ilike(f"%{_cat_name}%"),
                            Category.name_ar.ilike(f"%{_cat_name}%"),
                            Category.name_en.ilike(f"%{_cat_name}%"),
                        )
                    ).limit(1)
                )).first()
            if _cat_row:
                resolved_category_id = _cat_row[0]
                logger.info(f"[SEARCH] Resolved category '{_cat_name}' → {resolved_category_id}")

    # Primary text for semantic search embedding: use query_clean if modifiers were extracted, else resolved_query
    primary_text = query_clean or resolved_query
    query_script = _script_of(primary_text)

    t1 = time.time()
    logger.info(f"[TIMING] Normalization, Intent & Synonyms: {(t1-t0)*1000:.0f}ms")

    # 4. Gate expansion: run parallel expansion only for complex/intent queries
    has_synonym = len(synonym_variants) > 0
    should_expand = getattr(settings, "enable_query_expansion", True) and needs_expansion(query_text, query_script, has_synonym=has_synonym)

    if should_expand:
        # Use primary_text (query_clean from understanding) so expansion
        # generates variants for the core product term, not the raw query
        # with attribute modifiers that would conflict with JSONB filters.
        expansion_task = asyncio.create_task(
            query_expansion_service.expand_async(primary_text)
        )
        original_embed_task = asyncio.create_task(
            embedding_service.encode_text_async(primary_text, text_type="query")
        )
        expansion_result, original_embedding = await asyncio.gather(
            expansion_task, original_embed_task, return_exceptions=True
        )
        variants = expansion_result if isinstance(expansion_result, list) else []
        if isinstance(expansion_result, Exception):
            logger.warning(f"Query expansion skipped due to error: {expansion_result}")
    else:
        logger.info(f"[TIMING] Expansion skipped via needs_expansion (has_synonym={has_synonym}) for query '{query_text}'")
        variants = []
        original_embedding = await embedding_service.encode_text_async(primary_text, text_type="query")

    texts: List[str] = [primary_text]
    for candidate_t in [resolved_query, normalized_input, query_text]:
        if candidate_t and candidate_t not in texts:
            texts.append(candidate_t)

    for sv in synonym_variants:
        if sv and sv not in texts:
            texts.append(sv)

    if norm_arabicized and norm_arabicized not in texts:
        texts.append(norm_arabicized)

    for v in variants:
        nv = normalize_query(v) or v.strip()
        if nv and nv not in texts:
            texts.append(nv)

    logger.debug(
        "[SEARCH BRANCHES] query=%r  synonyms=%s  all_text_branches=%s",
        query_text, synonym_variants, texts,
    )

    t2 = time.time()
    logger.info(f"[TIMING] Expansion + first embed (parallel): {(t2-t1)*1000:.0f}ms")

    # 2. Batch-embed ONLY the new variants (original is already embedded)
    variant_texts = [t for t in texts if t != primary_text]
    if variant_texts:
        variant_embeddings = await embedding_service.embed_texts_batch(
            variant_texts, text_type="query"
        )
    else:
        variant_embeddings = []

    # Combine all embeddings
    all_embeddings = []
    if not isinstance(original_embedding, Exception) and original_embedding is not None:
        all_embeddings.append(original_embedding)
    elif isinstance(original_embedding, Exception):
        logger.warning(f"Original embedding error: {original_embedding}")

    all_embeddings.extend(variant_embeddings)

    primary_raw = (
        all_embeddings[0].tolist()
        if (all_embeddings and hasattr(all_embeddings[0], "tolist"))
        else (all_embeddings[0] if all_embeddings else [])
    )

    # Zero vectors (provider failure) are dropped — search degrades to the
    # remaining vectors, or to lexical-only ranking if none survive.
    query_vecs = [
        (e.tolist() if hasattr(e, "tolist") else e)
        for e in all_embeddings
        if (hasattr(e, "any") and e.any()) or (isinstance(e, list) and any(e))
    ]

    t3 = time.time()
    logger.info(f"[TIMING] Variant embeddings (batch): {(t3-t2)*1000:.0f}ms")

    # 3. Ranked branches + RRF (with attribute filters if extracted)
    fused = await _retrieve_fused_candidates(
        db=db,
        query_vecs=query_vecs,
        lexical_variants=texts,
        latitude=latitude,
        longitude=longitude,
        market_id=market_id,
        filters=filters,
        listing_type=effective_listing_type,
        extracted_attrs=extracted_attrs,
        category_id=resolved_category_id,
    )

    # Soft fallback: if attribute-filtered retrieval returns too few results,
    # re-run without attribute filters to avoid empty result pages.
    if extracted_attrs and len(fused) < 1:
        logger.info(
            f"[ATTR FALLBACK] Attribute-filtered retrieval returned {len(fused)} results "
            f"for query={query_text!r} attrs={extracted_attrs}. Retrying without filters."
        )
        fused = await _retrieve_fused_candidates(
            db=db,
            query_vecs=query_vecs,
            lexical_variants=texts,
            latitude=latitude,
            longitude=longitude,
            market_id=market_id,
            filters=filters,
            listing_type=effective_listing_type,
            extracted_attrs=None,
            category_id=resolved_category_id,
        )

    t4 = time.time()
    logger.info(f"[TIMING] Retrieval: {(t4-t3)*1000:.0f}ms")

    fused.sort(key=lambda x: x['rrf_score'], reverse=True)

    # ── Category boost: prioritize results matching the extracted category ──
    if intent_analysis and getattr(intent_analysis, 'category_name', None):
        cat = intent_analysis.category_name.lower()
        for r in fused:
            item_cat = (r.get('category') or '').lower()
            item_cat_ar = (r.get('category_name_ar') or '').lower()
            item_cat_en = (r.get('category_name_en') or '').lower()
            if cat in item_cat or cat in item_cat_ar or cat in item_cat_en:
                r['rrf_score'] *= 1.5  # 50% boost for category match
        fused.sort(key=lambda x: x['rrf_score'], reverse=True)
        logger.info(f"[SEARCH] Category boost applied for: {intent_analysis.category_name}")

    candidates = fused
    unique_item_ids_count = len(set(
        (c["result"].item_id if "result" in c else c.get("item_id"))
        for c in candidates
    ))
    logger.debug(f"[DEDUP PRE-RERANK] Before: {len(candidates)}, unique item_ids: {unique_item_ids_count}")

    candidates = _dedup_candidates(candidates, max_unique=50)
    logger.debug(f"[DEDUP PRE-RERANK] After: {len(candidates)} unique products")

    if synonym_variants and synonym_variants[0]:
        rerank_query = synonym_variants[0]
    elif arabicized and arabicized.strip() and arabicized.lower() != query_text.lower() and norm_arabicized:
        rerank_query = norm_arabicized
    else:
        rerank_query = normalized_input or query_text

    # Multi-query reranking: descriptive queries expand into concrete product
    # terms. The cross-encoder scores poorly on multi-term queries, so we rerank
    # against each variant separately and keep the best score per item.
    expansion_variants = variants if variants else []

    if expansion_variants and len(expansion_variants) >= 2:
        # Descriptive/intent query — rerank per variant IN PARALLEL, merge by max score
        import copy

        async def _rerank_one_variant(variant, cands, script):
            vc = copy.deepcopy(cands)
            return await _rerank_and_finalize(variant, vc, script, skip_score_gap=True)

        tasks = [_rerank_one_variant(v, candidates, query_script) for v in expansion_variants[:5]]
        all_variant_results = await asyncio.gather(*tasks, return_exceptions=True)

        best_by_id = {}
        for variant_scored in all_variant_results:
            if isinstance(variant_scored, Exception):
                logger.warning(f"Multi-rerank variant failed: {variant_scored}")
                continue
            for r in variant_scored:
                key = str(r.market_item_id)
                if key not in best_by_id or r.semantic_score > best_by_id[key].semantic_score:
                    best_by_id[key] = r

        scored = sorted(best_by_id.values(), key=lambda r: r.semantic_score, reverse=True)
        scored = scored[: settings.reranker_final_k]
        logger.info(f"[MULTI-RERANK] Merged {len(expansion_variants)} variants → {len(scored)} results (parallel)")
    else:
        scored = await _rerank_and_finalize(rerank_query, candidates, query_script, skip_score_gap=should_expand)

    t5 = time.time()
    logger.info(f"[TIMING] Reranker + Finalize: {(t5-t4)*1000:.0f}ms")
    logger.info(f"[TIMING] TOTAL _run_search: {(t5-t0)*1000:.0f}ms")

    was_intent_query = bool(expansion_variants and len(expansion_variants) >= 2) or should_expand

    # If results are strong enough to pass the strict exact-match threshold,
    # don't label them as "suggestions" — high-confidence results are exact
    # matches regardless of how the query was classified structurally.
    if was_intent_query and scored:
        strong_results = [r for r in scored if r.semantic_score >= settings.exact_tier_threshold]
        if len(strong_results) >= 3:
            was_intent_query = False

    return scored, primary_raw, was_intent_query


# ── POST /hybrid ────────────────────────────────────────────────
@router.post("/hybrid", response_model=HybridSearchResponse)
@limiter.limit("300/minute")
async def hybrid_search(
    request: Request,
    search_request: HybridSearchRequest,
    user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hybrid text search: multi-query Qwen3 semantic + Arabic tsvector lexical,
    fused with RRF, refined by the Qwen3 reranker, ordered language-aware.
    Single-pass tiering: exact → recommendations → SearchAlert.
    """
    try:
        if not _is_valid_query(search_request.query_text):
            logger.debug("[HYBRID SEARCH] Fast rejection for invalid query: %r", search_request.query_text)
            return HybridSearchResponse(
                found=False,
                action="request_more_details",
                search_mode="exact_matches",
                results=[],
            )

        # Check Redis L2 full search cache first
        cached = await get_cached_search(
            query=search_request.query_text,
            lat=search_request.latitude,
            lng=search_request.longitude,
            listing_type=search_request.listing_type,
        )
        if cached is not None:
            logger.info("[SEARCH] Returning L2 cached result — reranker skipped")
            return cached

        scored, primary_vec, was_intent_query = await _run_search(
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
        # Intent queries (expansion produced 2+ variants) get relaxed thresholds —
        # showing best-available beats empty results for discovery searches.
        # The mobile app renders these as "suggestions" instead of "exact_matches".
        if was_intent_query:
            exact_threshold = 0.15
            rec_threshold = 0.10
        else:
            exact_threshold = settings.exact_tier_threshold
            rec_threshold = settings.recommendation_tier_threshold

        exact = [r for r in scored if r.semantic_score >= exact_threshold]
        logger.debug(
            "[HYBRID SEARCH] query=%r  total_scored=%d  exact_tier_count=%d (threshold=%.2f)",
            search_request.query_text, len(scored), len(exact), exact_threshold,
        )

        response_obj: Optional[HybridSearchResponse] = None

        if len(exact) >= 3:
            guarded_exact = _filter_with_guards(exact, query_text=search_request.query_text, min_score_override=0.05 if was_intent_query else None)
            logger.debug(
                "[HYBRID SEARCH RETURN] query=%r  exact_returning=%d",
                search_request.query_text, len(guarded_exact),
            )
            response_obj = HybridSearchResponse(
                found=True,
                action=None,
                search_mode="suggestions" if was_intent_query else "exact_matches",
                results=guarded_exact,
            )
        else:
            # Not enough exact matches (< 3) — include recommendation tier items as well
            recommendations = [
                r for r in scored
                if r.semantic_score >= rec_threshold
            ]
            logger.debug(
                "[HYBRID SEARCH] query=%r  recommendations_tier_count=%d (threshold=%.2f)",
                search_request.query_text, len(recommendations), rec_threshold,
            )
            if recommendations:
                guarded_recs = _filter_with_guards(recommendations, query_text=search_request.query_text, min_score_override=0.05 if was_intent_query else None)
                response_obj = HybridSearchResponse(
                    found=True,
                    action=None if exact else ("suggestions" if was_intent_query else "recommendations"),
                    search_mode="suggestions" if was_intent_query else ("exact_matches" if exact else "recommendations"),
                    results=guarded_recs,
                )
            elif exact:
                guarded_exact = _filter_with_guards(exact, query_text=search_request.query_text, min_score_override=0.05 if was_intent_query else None)
                response_obj = HybridSearchResponse(
                    found=True,
                    action=None,
                    search_mode="suggestions" if was_intent_query else "exact_matches",
                    results=guarded_exact,
                )

        if response_obj is not None:
            await cache_search(
                query=search_request.query_text,
                lat=search_request.latitude,
                lng=search_request.longitude,
                listing_type=search_request.listing_type,
                result=response_obj,
            )
            return response_obj

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

        no_match_response = HybridSearchResponse(
            found=False,
            action="request_more_details",
            search_mode="exact_matches",
            results=[],
        )
        await cache_search(
            query=search_request.query_text,
            lat=search_request.latitude,
            lng=search_request.longitude,
            listing_type=search_request.listing_type,
            result=no_match_response,
        )
        return no_match_response

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
    user: Optional[User] = Depends(get_optional_current_user),
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
@limiter.limit("300/minute")
async def double_check_search(
    request: Request,
    search_request: DoubleCheckSearchRequest,
    user: Optional[User] = Depends(get_optional_current_user),
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

        scored, _, _intent = await _run_search(
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
