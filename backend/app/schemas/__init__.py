from app.schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    TokenResponse,
)
from app.schemas.shop import ShopCreate, ShopUpdate, ShopResponse
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    StockToggle,
)
from app.schemas.search import (
    TextSearchRequest,
    ImageSearchRequest,
    SearchResultItem,
    SearchResponse,
)
from app.schemas.special_offer import (
    SpecialOfferCreate,
    SpecialOfferUpdate,
    SpecialOfferResponse,
    CustomerSpecialOfferResponse,
)

__all__ = [
    "UserCreate", "UserLogin", "UserResponse", "TokenResponse",
    "ShopCreate", "ShopUpdate", "ShopResponse",
    "ProductCreate", "ProductUpdate", "ProductResponse", "StockToggle",
    "TextSearchRequest", "ImageSearchRequest", "SearchResultItem", "SearchResponse",
    "SpecialOfferCreate", "SpecialOfferUpdate", "SpecialOfferResponse", "CustomerSpecialOfferResponse",
]
