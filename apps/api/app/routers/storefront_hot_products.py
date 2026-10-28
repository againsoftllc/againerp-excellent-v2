"""Public Hot Products page (/hot-products)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.website_hot_products import (
    ensure_website_hot_products,
    load_json,
    normalize_hot_products_content,
)
from app.routers.storefront_products import _view_to_read
from app.schemas.website_hot_products import (
    HotProductsTab,
    StorefrontHotProductsData,
    StorefrontHotProductsResponse,
)
from app.services.ecommerce.storefront_catalog_service import StorefrontCatalogService

router = APIRouter(tags=["storefront-hot-products"])

STOREFRONT_CACHE = "private, no-store, max-age=0, must-revalidate"


def _resolve_hot_products(db: Session, content: dict):
    tabs = [HotProductsTab.model_validate(tab) for tab in (content.get("tabs") or [])]
    catalog = StorefrontCatalogService(db)
    views: dict[str, object] = {}
    tab_ids: dict[str, list[str]] = {}

    def add(view, tab_id: str) -> None:
        slug = (getattr(view, "slug", None) or "").strip()
        if not slug:
            return
        views[slug] = view
        current = tab_ids.setdefault(slug, [])
        if tab_id not in current:
            current.append(tab_id)

    for tab in tabs:
        if tab.hidden or tab.showAll:
            continue
        for slug in tab.productSlugs:
            view = catalog.get_by_slug(slug)
            if view:
                add(view, tab.id)
        for category_slug in tab.categorySlugs:
            try:
                result = catalog.list_products(category_slug=category_slug, per_page=48, page=1)
            except Exception:
                continue
            for view in result.items:
                add(view, tab.id)

    products = [_view_to_read(view) for view in views.values()]
    return tabs, products, tab_ids, list(views.keys())


@router.get("/hot-products", response_model=StorefrontHotProductsResponse)
def storefront_hot_products(
    response: Response, db: Session = Depends(get_db)
) -> StorefrontHotProductsResponse:
    response.headers["Cache-Control"] = STOREFRONT_CACHE
    row = ensure_website_hot_products(db)
    content = normalize_hot_products_content(load_json(row.content_json))
    tabs, products, tab_ids, slugs = _resolve_hot_products(db, content)
    curated = any(
        (not tab.hidden and not tab.showAll and (tab.categorySlugs or tab.productSlugs))
        for tab in tabs
    )
    return StorefrontHotProductsResponse(
        data=StorefrontHotProductsData(
            title=str(content.get("title") or "Hot Products"),
            subtitle=str(content.get("subtitle") or ""),
            bannerUrl=str(content.get("bannerUrl") or ""),
            tabs=tabs,
            productSlugs=slugs,
            curated=curated,
            products=products,
            productTabIds=tab_ids,
        )
    )
