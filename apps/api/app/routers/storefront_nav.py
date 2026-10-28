"""Public storefront category + brand nav (storefront chrome)."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.storefront import (
    StorefrontBrandNavRead,
    StorefrontBrandNavResponse,
    StorefrontCategoryNavNode,
    StorefrontCategoryNavResponse,
)
from app.services.ecommerce.storefront_catalog_service import StorefrontCatalogService

router = APIRouter(tags=["storefront-nav"])

STOREFRONT_CACHE = "public, max-age=60, s-maxage=120, stale-while-revalidate=300"


def _category_node(raw: dict) -> StorefrontCategoryNavNode:
    return StorefrontCategoryNavNode(
        id=raw["id"],
        slug=raw["slug"],
        name=raw["name"],
        parent_id=raw.get("parent_id"),
        icon_url=raw.get("icon_url"),
        banner_url=raw.get("banner_url"),
        show_in_top_menu=bool(raw.get("show_in_top_menu", False)),
        china_search_keyword=raw.get("china_search_keyword"),
        children=[_category_node(child) for child in raw.get("children", [])],
    )


@router.get("/categories", response_model=StorefrontCategoryNavResponse)
def storefront_categories(
    response: Response,
    db: Session = Depends(get_db),
    channel: Optional[Literal["catalog", "dropshipping"]] = Query(
        default="dropshipping",
        description="catalog = Catalog → Categories · dropshipping = Dropshipping frontstore tree",
    ),
) -> StorefrontCategoryNavResponse:
    response.headers["Cache-Control"] = STOREFRONT_CACHE
    tree = StorefrontCatalogService(db).list_categories(channel=channel or "dropshipping")
    return StorefrontCategoryNavResponse(data=[_category_node(node) for node in tree])


@router.get("/brands", response_model=StorefrontBrandNavResponse)
def storefront_brands(response: Response, db: Session = Depends(get_db)) -> StorefrontBrandNavResponse:
    response.headers["Cache-Control"] = STOREFRONT_CACHE
    brands = StorefrontCatalogService(db).list_brands()
    return StorefrontBrandNavResponse(data=[StorefrontBrandNavRead(**b) for b in brands])
