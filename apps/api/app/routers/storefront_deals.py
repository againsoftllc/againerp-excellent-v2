"""Public Excellent Tech Deals page (tabs on /offers-and-deals)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.website_deals_page import (
    ensure_website_deals_page,
    load_json,
    normalize_deals_content,
)
from app.schemas.website_deals import DealsPageContent, StorefrontDealsPageResponse

router = APIRouter(tags=["storefront-deals"])

STOREFRONT_CACHE = "public, max-age=30, s-maxage=60, stale-while-revalidate=120"


@router.get("/deals-page", response_model=StorefrontDealsPageResponse)
def storefront_deals_page(
    response: Response, db: Session = Depends(get_db)
) -> StorefrontDealsPageResponse:
    response.headers["Cache-Control"] = STOREFRONT_CACHE
    row = ensure_website_deals_page(db)
    content = DealsPageContent.model_validate(normalize_deals_content(load_json(row.content_json)))
    return StorefrontDealsPageResponse(data=content)
