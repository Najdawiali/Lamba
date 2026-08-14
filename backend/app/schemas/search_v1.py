"""
Pydantic schemas for V1 Hybrid Search with advanced faceted filtering, fallback logic, and alerts.
"""

import uuid
from typing import Optional, List
from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    max_distance_km: Optional[float] = Field(None, ge=0.0, description="Geographic proximity radius limit in kilometers")
    business_nature: Optional[str] = Field(None, description="Shop business nature/classification (e.g. Roastery, Grocery)")
    category_id: Optional[uuid.UUID] = Field(None, description="Granular category or subcategory filter")
    in_stock_only: Optional[bool] = Field(None, description="Only return items currently in stock")
    price_min: Optional[float] = Field(None, ge=0.0, description="Minimum item price filter")
    price_max: Optional[float] = Field(None, ge=0.0, description="Maximum item price filter")
    city: Optional[str] = Field(None, description="Physical city refinement filter")


class HybridSearchRequest(BaseModel):
    query_text: str = Field(..., min_length=1, description="Natural language search query")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="User's latitude coordinate")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="User's longitude coordinate")
    market_id: Optional[uuid.UUID] = Field(None, description="Optional market ID to filter results locally")
    user_id: Optional[uuid.UUID] = Field(None, description="Optional user ID to associate search alerts")
    listing_type: Optional[str] = Field(None, description="Filter by listing type: 'product' or 'service'")
    filters: Optional[SearchFilters] = Field(None, description="Granular filtering parameters")


class DoubleCheckSearchRequest(BaseModel):
    original_query_text: str = Field(..., min_length=1, description="The original search query")
    user_refined_details: str = Field(..., min_length=1, description="User provided details to refine search")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="User's latitude coordinate")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="User's longitude coordinate")
    market_id: Optional[uuid.UUID] = Field(None, description="Optional market ID to filter results locally")
    listing_type: Optional[str] = Field(None, description="Filter by listing type: 'product' or 'service'")


class HybridSearchResultItem(BaseModel):
    item_id: uuid.UUID
    market_item_id: uuid.UUID
    name: str
    name_ar: Optional[str] = None
    name_en: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    category_name_ar: Optional[str] = None
    category_name_en: Optional[str] = None
    listing_type: Optional[str] = "product"
    image_url: Optional[str] = None
    price: Optional[float] = None
    stock_count: int
    in_stock: bool
    
    # Market Details
    market_id: uuid.UUID
    market_name: str
    market_address: str
    market_phone: Optional[str] = None
    phone: Optional[str] = None
    latitude: float
    longitude: float
    market_is_open: bool
    
    # Proximity & Semantic Scores
    distance_km: float
    semantic_score: float
    proximity_score: float
    final_score: float

    model_config = {"from_attributes": True}


class HybridSearchResponse(BaseModel):
    found: bool
    action: Optional[str] = None  # "request_more_details" if empty, "recommendations" if fallback
    search_mode: str = Field("exact_matches", description="'exact_matches' or 'recommendations'")
    results: List[HybridSearchResultItem] = []
