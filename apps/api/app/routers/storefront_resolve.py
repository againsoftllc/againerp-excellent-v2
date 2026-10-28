"""Flat URL slug resolution for storefront routing (STEP 04)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.storefront_content import find_published_website_page
from typing import Optional

from app.deps.auth import get_optional_user
from app.models.auth_user import AuthUser
from app.routers.storefront_products import (
    _attach_review_stats,
    _detail_from_ec,
    _is_staff_preview,
)
from app.schemas.storefront import (
    StorefrontBrandResolve,
    StorefrontCategoryResolve,
    StorefrontSlugResolveResponse,
)
from app.services.ecommerce.storefront_catalog_service import StorefrontCatalogService

router = APIRouter(prefix="/resolve", tags=["storefront-resolve"])

STOREFRONT_CACHE = "public, max-age=60, s-maxage=120, stale-while-revalidate=300"


@router.get("/{slug}", response_model=StorefrontSlugResolveResponse)
def resolve_storefront_slug(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
    user: Optional[AuthUser] = Depends(get_optional_user),
) -> StorefrontSlugResolveResponse:
    # Slug resolution is the first gate the shop hits, so it has to honour a
    # staff preview too — otherwise a Private product 404s before the product
    # endpoint is ever reached.
    preview = _is_staff_preview(user)
    response.headers["Cache-Control"] = "private, no-store" if preview else STOREFRONT_CACHE
    normalized = slug.strip().lower()
    if not normalized:
        raise HTTPException(status_code=404, detail="Not found")

    service = StorefrontCatalogService(db, include_private=preview)
    resolved = service.resolve_slug(normalized)
    if not resolved:
        # Marketing campaigns (Offer / Happy Hour) live outside the catalog
        # domain `service.resolve_slug` covers above — check them here so a
        # campaign created after the storefront's build-time bundle still
        # resolves instead of 404ing. Full public/date-window visibility is
        # re-checked by the page itself; this only asks "does this slug
        # belong to something that isn't explicitly off".
        from app.models.marketing_offer import MarketingOffer
        from app.models.marketing_happy_hour import MarketingHappyHour

        offer = db.query(MarketingOffer).filter(MarketingOffer.slug == normalized).first()
        if offer and offer.status not in {"disabled", "draft"}:
            return StorefrontSlugResolveResponse(type="offer", slug=normalized)

        happy_hour = (
            db.query(MarketingHappyHour).filter(MarketingHappyHour.slug == normalized).first()
        )
        if happy_hour and happy_hour.status not in {"disabled", "draft"}:
            return StorefrontSlugResolveResponse(type="happy_hour", slug=normalized)

        page = find_published_website_page(db, normalized)
        if page:
            return StorefrontSlugResolveResponse(type="page", slug=page.slug)
        raise HTTPException(status_code=404, detail="Not found")

    entity_type = resolved["type"]
    if entity_type == "product":
        ec = service.get_ec_by_slug(normalized)
        view = service.get_by_slug(normalized)
        if not view or not ec:
            raise HTTPException(status_code=404, detail="Not found")
        detail = _detail_from_ec(view, ec, db)
        if resolved.get("seo_title") and not detail.seo_title:
            detail = detail.model_copy(update={"seo_title": resolved["seo_title"]})
        if resolved.get("seo_description") and not detail.seo_description:
            detail = detail.model_copy(update={"seo_description": resolved["seo_description"]})
        related = _attach_review_stats(db, service.related(normalized))
        return StorefrontSlugResolveResponse(
            type="product",
            slug=normalized,
            product=detail,
            related=related,
        )

    if entity_type == "category":
        cat = resolved["category"]
        return StorefrontSlugResolveResponse(
            type="category",
            slug=normalized,
            category=StorefrontCategoryResolve(**cat),
        )

    if entity_type == "brand":
        brand = resolved["brand"]
        return StorefrontSlugResolveResponse(
            type="brand",
            slug=normalized,
            brand=StorefrontBrandResolve(**brand),
        )

    raise HTTPException(status_code=404, detail="Not found")
