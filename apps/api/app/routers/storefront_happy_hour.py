"""Public storefront Happy Hour campaign page."""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.catalog_product_special import in_daily_window
from app.models.marketing_happy_hour import MarketingHappyHour, MarketingHappyHourSection
from app.services.ecommerce.storefront_catalog_service import StorefrontCatalogService

router = APIRouter(tags=["storefront-happy-hour"])

STOREFRONT_CACHE = "public, max-age=30"
DEFAULT_SLUG = "happy-hour"


def _set_cache(response: Response, value: str = STOREFRONT_CACHE) -> None:
    response.headers["Cache-Control"] = value


def _fmt_display(dt: datetime) -> str:
    return dt.strftime("%d %b %Y")


def _fmt_iso(dt: datetime) -> str:
    return dt.isoformat()


def _terms_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    return []


def _is_public(row: MarketingHappyHour, now: datetime) -> bool:
    if row.status in {"disabled", "draft", "ended"}:
        return False
    if row.status == "running":
        return True
    if row.status == "scheduled":
        return row.starts_at <= now <= row.ends_at
    return row.starts_at <= now <= row.ends_at


class StorefrontHappyHourDealProduct(BaseModel):
    id: str
    item_id: str
    slug: str
    name: str
    price: float
    compare_at_price: Optional[float] = None
    thumbnail: Optional[str] = None
    brand: Optional[str] = None
    in_stock: bool = True
    note: Optional[str] = None


class StorefrontHappyHourSection(BaseModel):
    key: str
    label: str
    products: List[StorefrontHappyHourDealProduct]


class StorefrontHappyHourDetail(BaseModel):
    slug: str
    title: str
    subtitle: Optional[str] = None
    description: str
    startDate: str
    endDate: str
    startDateISO: str
    endDateISO: str
    dailyStartHour: int
    dailyEndHour: int
    outletLabel: str
    terms: List[str]
    sections: List[StorefrontHappyHourSection]


class StorefrontHappyHourResponse(BaseModel):
    data: StorefrontHappyHourDetail


def _detail(db: Session, row: MarketingHappyHour) -> StorefrontHappyHourDetail:
    catalog = StorefrontCatalogService(db)
    sections: List[StorefrontHappyHourSection] = []
    # Outside tonight's window the page still shows (title, countdown, terms)
    # so shoppers know when it opens, but no product/price is listed yet —
    # matches the price-side nightly gating already applied on the PDP.
    live_now = in_daily_window(datetime.utcnow(), row.daily_start_hour, row.daily_end_hour)
    if live_now:
        from app.models.catalog_product import CatalogProduct

        all_slugs = {
            (deal.product_slug or "").strip()
            for section in row.sections or []
            for deal in section.deals or []
            if (deal.product_slug or "").strip()
        }
        raw_by_slug = {
            p.slug: p
            for p in (
                db.query(CatalogProduct).filter(CatalogProduct.slug.in_(all_slugs)).all()
                if all_slugs
                else []
            )
        }
        for section in sorted(row.sections or [], key=lambda s: (s.sort_order, s.label)):
            products: List[StorefrontHappyHourDealProduct] = []
            for deal in sorted(
                section.deals or [], key=lambda d: (d.priority or 0, d.sort_order, d.product_slug)
            ):
                slug = (deal.product_slug or "").strip()
                if not slug:
                    continue
                # Disabled = its quota sold out (or the admin turned it off) —
                # stop showing it on the campaign page, same as removing it.
                if not deal.enabled:
                    continue
                view = catalog.get_by_slug(slug)
                if not view:
                    continue
                # The "regular" reference must be the product's raw list price,
                # never the already-resolved `view.price` — otherwise once this
                # very deal is the active special, offer == view.price and the
                # product wrongly looks like a non-discount and gets dropped.
                raw = raw_by_slug.get(slug)
                if raw is not None:
                    regular = float(raw.compare_at_price) if raw.compare_at_price else float(raw.price)
                else:
                    regular = (
                        float(view.compare_at_price) if view.compare_at_price is not None else float(view.price)
                    )
                offer = float(deal.offer_price)
                if offer <= 0 or offer >= regular:
                    continue
                products.append(
                    StorefrontHappyHourDealProduct(
                        id=view.id,
                        item_id=view.item_id,
                        slug=view.slug,
                        name=view.name,
                        price=offer,
                        compare_at_price=regular,
                        thumbnail=view.thumbnail,
                        brand=view.brand or None,
                        in_stock=bool(view.in_stock),
                        note=(deal.note or None),
                    )
                )
            if not products:
                continue
            sections.append(
                StorefrontHappyHourSection(
                    key=section.key,
                    label=section.label,
                    products=products,
                )
            )
    return StorefrontHappyHourDetail(
        slug=row.slug,
        title=row.title,
        subtitle=row.subtitle,
        description=row.description or "",
        startDate=_fmt_display(row.starts_at),
        endDate=_fmt_display(row.ends_at),
        startDateISO=_fmt_iso(row.starts_at),
        endDateISO=_fmt_iso(row.ends_at),
        dailyStartHour=int(row.daily_start_hour or 22),
        dailyEndHour=int(row.daily_end_hour or 24),
        outletLabel=row.outlet_label or "Online Only",
        terms=_terms_list(row.terms_json),
        sections=sections,
    )


@router.get("/happy-hour", response_model=StorefrontHappyHourResponse)
def get_happy_hour(
    response: Response,
    db: Session = Depends(get_db),
) -> StorefrontHappyHourResponse:
    """Active Happy Hour campaign (slug `happy-hour`, else first public running)."""
    _set_cache(response)
    now = datetime.utcnow()
    opts = joinedload(MarketingHappyHour.sections).joinedload(MarketingHappyHourSection.deals)

    row = (
        db.query(MarketingHappyHour)
        .options(opts)
        .filter(MarketingHappyHour.slug == DEFAULT_SLUG)
        .first()
    )
    if row and not _is_public(row, now):
        row = None

    if not row:
        rows = (
            db.query(MarketingHappyHour)
            .options(opts)
            .order_by(MarketingHappyHour.sort_order.asc(), MarketingHappyHour.starts_at.desc())
            .all()
        )
        for candidate in rows:
            if _is_public(candidate, now) and candidate.starts_at <= now <= candidate.ends_at:
                row = candidate
                break
            if candidate.status == "running":
                row = candidate
                break

    if not row:
        raise HTTPException(status_code=404, detail="Happy Hour not found")
    return StorefrontHappyHourResponse(data=_detail(db, row))


class StorefrontHappyHourSummary(BaseModel):
    slug: str
    title: str
    subtitle: Optional[str] = None
    status: str
    startDateISO: str
    endDateISO: str


class StorefrontHappyHourListResponse(BaseModel):
    data: List[StorefrontHappyHourSummary]


@router.get("/happy-hours", response_model=StorefrontHappyHourListResponse)
def list_happy_hours(response: Response, db: Session = Depends(get_db)) -> StorefrontHappyHourListResponse:
    """Public (not draft / disabled / ended) campaigns — lets a storefront pick one by slug."""
    _set_cache(response)
    now = datetime.utcnow()
    rows = db.query(MarketingHappyHour).order_by(MarketingHappyHour.sort_order.asc(), MarketingHappyHour.starts_at.desc()).all()
    return StorefrontHappyHourListResponse(
        data=[
            StorefrontHappyHourSummary(
                slug=row.slug,
                title=row.title,
                subtitle=row.subtitle,
                status=row.status,
                startDateISO=_fmt_iso(row.starts_at),
                endDateISO=_fmt_iso(row.ends_at),
            )
            for row in rows
            if _is_public(row, now)
        ]
    )


@router.get("/happy-hours/{slug}", response_model=StorefrontHappyHourResponse)
def get_happy_hour_by_slug(slug: str, response: Response, db: Session = Depends(get_db)) -> StorefrontHappyHourResponse:
    """One public campaign by slug (the storefront's homepage deals can point at any of them)."""
    _set_cache(response)
    opts = joinedload(MarketingHappyHour.sections).joinedload(MarketingHappyHourSection.deals)
    row = db.query(MarketingHappyHour).options(opts).filter(MarketingHappyHour.slug == slug).first()
    if not row or not _is_public(row, datetime.utcnow()):
        raise HTTPException(status_code=404, detail="Happy Hour not found")
    return StorefrontHappyHourResponse(data=_detail(db, row))
