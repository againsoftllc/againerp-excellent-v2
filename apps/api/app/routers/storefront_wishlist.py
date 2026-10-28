"""Storefront wishlist and saved-for-later APIs — website_wishlists / website_wishlist_items."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.storefront_customer_auth import (
    CustomerAuthContext,
    get_optional_storefront_customer,
)
from app.models.website_wishlist import WebsiteWishlist
from app.services.ecommerce.website_wishlist_service import WishlistError, WebsiteWishlistService
from app.services.ecommerce.storefront_feature_flags import require_storefront_flag

WISHLIST_HEADER = "X-Wishlist-Token"
SAVED_HEADER = "X-Saved-Token"
STOREFRONT_CACHE = "private, no-store"


class WishlistItemCreate(BaseModel):
    product_id: str = Field(min_length=1, max_length=36)


class WishlistItemRead(BaseModel):
    id: str
    product_id: str
    item_id: Optional[str] = None
    slug: str
    name: str
    thumbnail: Optional[str] = None
    unit_price: float
    compare_at_price: Optional[float] = None
    discount_pct: Optional[int] = None
    rating: float = 0


class WishlistRead(BaseModel):
    wishlist_token: str
    customer_id: Optional[str] = None
    item_count: int
    items: List[WishlistItemRead]


class WishlistResponse(BaseModel):
    data: WishlistRead


def _service(db: Session) -> WebsiteWishlistService:
    return WebsiteWishlistService(db)


def _customer_id(ctx: Optional[CustomerAuthContext]) -> Optional[str]:
    if ctx is None:
        return None
    return ctx[2].id


def _make_router(prefix: str, token_header: str, kind: str, tag: str) -> APIRouter:
    """The list endpoints for one kind of list (the wishlist, or saved-for-later)."""
    r = APIRouter(prefix=prefix, tags=[tag])

    def get_list_context(
        response: Response,
        db: Session = Depends(get_db),
        token: Optional[str] = Header(default=None, alias=token_header),
        ctx: Optional[CustomerAuthContext] = Depends(get_optional_storefront_customer),
    ) -> WebsiteWishlist:
        require_storefront_flag("wishlist")
        response.headers["Cache-Control"] = STOREFRONT_CACHE
        return _service(db).get_or_create(
            wishlist_token=token,
            customer_id=_customer_id(ctx),
            kind=kind,
        )

    @r.get("", response_model=WishlistResponse)
    def get_list(wishlist: WebsiteWishlist = Depends(get_list_context), db: Session = Depends(get_db)) -> WishlistResponse:
        return WishlistResponse(data=WishlistRead(**_service(db).build_read(wishlist)))

    @r.post("/items", response_model=WishlistResponse)
    def add_item(
        payload: WishlistItemCreate,
        wishlist: WebsiteWishlist = Depends(get_list_context),
        db: Session = Depends(get_db),
    ) -> WishlistResponse:
        try:
            wishlist = _service(db).add_product(wishlist, payload.product_id)
        except WishlistError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return WishlistResponse(data=WishlistRead(**_service(db).build_read(wishlist)))

    @r.delete("/items/{product_id}", response_model=WishlistResponse)
    def remove_item(
        product_id: str,
        wishlist: WebsiteWishlist = Depends(get_list_context),
        db: Session = Depends(get_db),
    ) -> WishlistResponse:
        try:
            wishlist = _service(db).remove_product(wishlist, product_id)
        except WishlistError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return WishlistResponse(data=WishlistRead(**_service(db).build_read(wishlist)))

    @r.delete("", response_model=WishlistResponse)
    def clear_list(
        wishlist: WebsiteWishlist = Depends(get_list_context),
        db: Session = Depends(get_db),
    ) -> WishlistResponse:
        wishlist = _service(db).clear(wishlist)
        return WishlistResponse(data=WishlistRead(**_service(db).build_read(wishlist)))

    return r


router = _make_router("/wishlist", WISHLIST_HEADER, "wishlist", "storefront-wishlist")
# "Save" on the product page: a separate save-for-later list, same rules as the wishlist.
saved_router = _make_router("/saved", SAVED_HEADER, "saved", "storefront-saved")
