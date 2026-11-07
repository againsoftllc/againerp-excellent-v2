"""Public storefront deal / offer landing pages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.catalog_product_special import in_daily_window
from app.models.marketing_offer import MarketingOffer, MarketingOfferSection
from app.services.ecommerce.storefront_catalog_service import StorefrontCatalogService

router = APIRouter(tags=["storefront-offer-pages"])

STOREFRONT_CACHE = "public, max-age=30"


def _set_cache(response: Response, value: str = STOREFRONT_CACHE) -> None:
    response.headers["Cache-Control"] = value


def _fmt_display(dt: datetime) -> str:
    return dt.strftime("%d %b %Y")


def _fmt_iso(dt: datetime) -> str:
    return dt.isoformat()


def _terms_list(raw: str | None) -> list[str]:
    import json

    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    return []


# Times are stored as UTC; the shop is in Bangladesh (UTC+6, no daylight saving), so that is how a start is written out.
_DHAKA = timezone(timedelta(hours=6))


def _starts_label(dt: datetime) -> str:
    """"11 Nov 2026, 12:00 AM" in Dhaka time."""
    return dt.replace(tzinfo=timezone.utc).astimezone(_DHAKA).strftime("%d %b %Y, %I:%M %p")


def _state(row: MarketingOffer, now: datetime) -> Optional[str]:
    """"live" (shown with its products), "upcoming" (a scheduled offer that has not started: its page shows the
    countdown and the description only) or None (not shown at all)."""
    if row.status in {"disabled", "draft", "ended"}:
        return None
    if row.status == "running":
        return "live"
    if now < row.starts_at:
        return "upcoming" if row.status == "scheduled" else None
    return "live" if now <= row.ends_at else None


def _is_public(row: MarketingOffer, now: datetime) -> bool:
    """Running now (what the popups use): an upcoming offer is not public yet."""
    return _state(row, now) == "live"


class StorefrontOfferSummary(BaseModel):
    slug: str
    title: str
    subtitle: Optional[str] = None
    description: str
    image: str
    # When set, the storefront sends shoppers here instead of this offer's
    # own product-grid page — both the "View Details" card link and a direct
    # visit to the offer's own URL redirect to it.
    customLink: Optional[str] = None
    startDate: str
    endDate: str
    startDateISO: str
    endDateISO: str
    # "live" | "upcoming": an upcoming offer has not started yet (the storefront shows "Starts in ..." and no products).
    status: str = "live"
    # The start as shown to shoppers, in Dhaka time ("11 Nov 2026, 12:00 AM").
    startsAtLabel: str = ""
    dailyStartHour: Optional[int] = None
    dailyEndHour: Optional[int] = None
    outletLabel: str


class StorefrontOfferProduct(BaseModel):
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


class StorefrontOfferSection(BaseModel):
    key: str
    label: str
    products: List[StorefrontOfferProduct]


class StorefrontOfferDetail(StorefrontOfferSummary):
    terms: List[str]
    sections: List[StorefrontOfferSection]


class StorefrontOfferListResponse(BaseModel):
    data: List[StorefrontOfferSummary]


class StorefrontOfferDetailResponse(BaseModel):
    data: StorefrontOfferDetail


def _summary(row: MarketingOffer, state: str = "live") -> StorefrontOfferSummary:
    return StorefrontOfferSummary(
        slug=row.slug,
        title=row.title,
        subtitle=row.subtitle,
        description=row.description or "",
        image=row.image_url or "/images/offers/placeholder.svg",
        customLink=row.custom_link,
        startDate=_fmt_display(row.starts_at),
        endDate=_fmt_display(row.ends_at),
        startDateISO=_fmt_iso(row.starts_at),
        endDateISO=_fmt_iso(row.ends_at),
        status=state,
        startsAtLabel=_starts_label(row.starts_at),
        dailyStartHour=row.daily_start_hour,
        dailyEndHour=row.daily_end_hour,
        outletLabel=row.outlet_label or "All Outlet",
    )


def _detail(db: Session, row: MarketingOffer, state: str = "live") -> StorefrontOfferDetail:
    """Hand-picked deals, same shape as storefront_happy_hour.py `_detail`.
    Outside the (optional) nightly window the sections come back empty — the
    page itself (title/countdown/terms) still shows so shoppers know when it
    opens, same nightly gating as Happy Hour."""
    catalog = StorefrontCatalogService(db)
    sections: List[StorefrontOfferSection] = []
    live_now = state == "live"  # an offer runs its whole date range; before it starts nothing but the countdown is shown
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
            products: List[StorefrontOfferProduct] = []
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
                # Every deal is listed. "Regular" = what the product normally sells for (the raw price, never the
                # already-resolved `view.price`, which carries this deal once it is the active special). The offer price
                # shows when it is below the regular one, else the regular price: an offer never raises a price.
                raw = raw_by_slug.get(slug)
                regular = float(raw.price) if raw is not None else float(view.compare_at_price if view.compare_at_price is not None else view.price)
                list_price = float(raw.compare_at_price) if raw is not None and raw.compare_at_price else (float(view.compare_at_price) if view.compare_at_price is not None else None)
                offer = float(deal.offer_price)
                shown = offer if 0 < offer < regular else regular
                strike = list_price if list_price is not None and list_price > shown else (regular if shown < regular else None)
                products.append(
                    StorefrontOfferProduct(
                        id=view.id,
                        item_id=view.item_id,
                        slug=view.slug,
                        name=view.name,
                        price=shown,
                        compare_at_price=strike,
                        thumbnail=view.thumbnail,
                        brand=view.brand or None,
                        in_stock=bool(view.in_stock),
                        note=(deal.note or None),
                    )
                )
            if not products:
                continue
            sections.append(
                StorefrontOfferSection(
                    key=section.key,
                    label=section.label,
                    products=products,
                )
            )
    base = _summary(row, state)
    terms = _terms_list(row.terms_json) if live_now else []
    return StorefrontOfferDetail(**base.model_dump(), terms=terms, sections=sections)


@router.get("/offer-pages", response_model=StorefrontOfferListResponse)
def list_offer_pages(response: Response, db: Session = Depends(get_db)) -> StorefrontOfferListResponse:
    _set_cache(response)
    now = datetime.utcnow()
    rows = (
        db.query(MarketingOffer)
        .options(joinedload(MarketingOffer.sections).joinedload(MarketingOfferSection.deals))
        .order_by(MarketingOffer.sort_order.asc(), MarketingOffer.starts_at.desc())
        .all()
    )
    states = [(row, _state(row, now)) for row in rows]
    live = [row for row, st in states if st == "live" and row.starts_at <= now <= row.ends_at]
    upcoming = sorted((row for row, st in states if st == "upcoming"), key=lambda r: r.starts_at)
    # running now first, then what is coming (soonest first)
    return StorefrontOfferListResponse(data=[_summary(row, "live") for row in live] + [_summary(row, "upcoming") for row in upcoming])


@router.get("/offer-pages/{slug}", response_model=StorefrontOfferDetailResponse)
def get_offer_page(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
) -> StorefrontOfferDetailResponse:
    _set_cache(response)
    clean = slug.strip().strip("/")
    row = (
        db.query(MarketingOffer)
        .options(joinedload(MarketingOffer.sections).joinedload(MarketingOfferSection.deals))
        .filter(MarketingOffer.slug == clean)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Offer not found")
    state = _state(row, datetime.utcnow())
    if state is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    return StorefrontOfferDetailResponse(data=_detail(db, row, state))
