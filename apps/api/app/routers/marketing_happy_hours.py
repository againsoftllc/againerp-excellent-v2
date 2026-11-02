from __future__ import annotations

import json
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.database import engine, get_db
from app.deps.auth import require_write_access
from app.models.marketing_happy_hour import (
    MarketingHappyHour,
    MarketingHappyHourDeal,
    MarketingHappyHourSection,
)
from app.schemas.marketing_happy_hour import (
    HappyHourCreate,
    HappyHourDealRead,
    HappyHourListMeta,
    HappyHourListResponse,
    HappyHourRead,
    HappyHourResponse,
    HappyHourSectionInput,
    HappyHourSectionRead,
    HappyHourUpdate,
)

router = APIRouter(prefix="/marketing/happy-hours", tags=["marketing-happy-hours"])


def ensure_marketing_happy_hour_columns() -> None:
    """Deal priority (OpenCart-style: lowest number wins display order/tie-break)
    + deal quota (quantity) and its enabled toggle."""
    statements = [
        "ALTER TABLE marketing_happy_hour_deals ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE marketing_happy_hour_deals ADD COLUMN IF NOT EXISTS quantity INTEGER",
        "ALTER TABLE marketing_happy_hour_deals ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-") or "section"


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


def _quantity_sold_by_slug(db: Session, campaign_id: str) -> dict[str, int]:
    """quantity_sold lives on the synced catalog_product_specials row (checkout
    increments it there), not on the deal — read it back for display."""
    from app.models.catalog_product import CatalogProduct
    from app.models.catalog_product_special import CatalogProductSpecial

    rows = (
        db.query(CatalogProductSpecial.quantity_sold, CatalogProduct.slug)
        .join(CatalogProduct, CatalogProduct.id == CatalogProductSpecial.product_id)
        .filter(CatalogProductSpecial.happy_hour_campaign_id == campaign_id)
        .all()
    )
    return {slug: int(sold or 0) for sold, slug in rows}


def _to_read(db: Session, row: MarketingHappyHour) -> HappyHourRead:
    sections = sorted(row.sections or [], key=lambda s: (s.sort_order, s.label))
    sold_by_slug = _quantity_sold_by_slug(db, row.id)
    return HappyHourRead(
        id=row.id,
        company_id=row.company_id,
        slug=row.slug,
        title=row.title,
        subtitle=row.subtitle,
        description=row.description or "",
        outlet_label=row.outlet_label or "Online Only",
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        daily_start_hour=int(row.daily_start_hour or 22),
        daily_end_hour=int(row.daily_end_hour or 24),
        status=row.status,
        terms=_terms_list(row.terms_json),
        sort_order=row.sort_order,
        sections=[
            HappyHourSectionRead(
                id=s.id,
                key=s.key,
                label=s.label,
                sort_order=s.sort_order,
                deals=[
                    HappyHourDealRead(
                        id=d.id,
                        product_slug=d.product_slug,
                        offer_price=float(d.offer_price),
                        note=d.note,
                        priority=int(d.priority or 0),
                        quantity=d.quantity,
                        quantity_sold=sold_by_slug.get(d.product_slug, 0),
                        enabled=bool(d.enabled),
                        sort_order=d.sort_order,
                    )
                    for d in sorted(
                        s.deals or [], key=lambda x: (x.priority or 0, x.sort_order, x.product_slug)
                    )
                ],
            )
            for s in sections
        ],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _replace_sections(db: Session, campaign: MarketingHappyHour, sections: List[HappyHourSectionInput]) -> None:
    campaign.sections.clear()
    db.flush()
    seen: set[str] = set()
    for index, item in enumerate(sections):
        key = (item.key or _slugify(item.label)).strip()
        if not key or key in seen:
            key = f"{key or 'section'}-{index + 1}"
        seen.add(key)
        section = MarketingHappyHourSection(
            key=key,
            label=item.label.strip(),
            sort_order=item.sort_order if item.sort_order is not None else index,
        )
        for d_index, deal in enumerate(item.deals or []):
            slug = deal.product_slug.strip()
            if not slug or deal.offer_price <= 0:
                continue
            section.deals.append(
                MarketingHappyHourDeal(
                    product_slug=slug,
                    offer_price=float(deal.offer_price),
                    note=(deal.note or "").strip() or None,
                    priority=deal.priority if deal.priority is not None else 0,
                    quantity=deal.quantity,
                    enabled=deal.enabled if deal.enabled is not None else True,
                    sort_order=deal.sort_order if deal.sort_order is not None else d_index,
                )
            )
        campaign.sections.append(section)


def sync_happy_hour_deal_priority(
    db: Session, campaign_id: str, product_slug: str, priority: int
) -> None:
    """Bidirectional sync: the product-form's Special Price table edited this
    mirrored row's priority — push it into the source Happy Hour deal so the
    next campaign save (which rebuilds specials from deals) doesn't revert it."""
    deal = (
        db.query(MarketingHappyHourDeal)
        .join(MarketingHappyHourSection, MarketingHappyHourDeal.section_id == MarketingHappyHourSection.id)
        .filter(
            MarketingHappyHourSection.campaign_id == campaign_id,
            MarketingHappyHourDeal.product_slug == product_slug,
        )
        .first()
    )
    if deal and deal.priority != priority:
        deal.priority = priority
        db.flush()


def disable_happy_hour_deal_by_slug(db: Session, campaign_id: str, product_slug: str) -> None:
    """Called when this deal's mirrored special sells out its quota (see
    storefront_checkout_service._consume_special_quota) — turns the deal off
    so its price stops applying, without removing it from the section."""
    deal = (
        db.query(MarketingHappyHourDeal)
        .join(MarketingHappyHourSection, MarketingHappyHourDeal.section_id == MarketingHappyHourSection.id)
        .filter(
            MarketingHappyHourSection.campaign_id == campaign_id,
            MarketingHappyHourDeal.product_slug == product_slug,
        )
        .first()
    )
    if deal and deal.enabled:
        deal.enabled = False
        db.flush()


def remove_happy_hour_deal_by_slug(db: Session, campaign_id: str, product_slug: str) -> None:
    """The product-form removed this product's mirrored special row — drop the
    matching deal from the campaign too, else the next campaign save would
    just re-create the mirror."""
    deal = (
        db.query(MarketingHappyHourDeal)
        .join(MarketingHappyHourSection, MarketingHappyHourDeal.section_id == MarketingHappyHourSection.id)
        .filter(
            MarketingHappyHourSection.campaign_id == campaign_id,
            MarketingHappyHourDeal.product_slug == product_slug,
        )
        .first()
    )
    if deal:
        db.delete(deal)
        db.flush()


def _sync_specials_for_campaign(db: Session, campaign: MarketingHappyHour) -> None:
    """Mirror every current deal into `catalog_product_specials` (so the regular
    product page / category listing resolve to the same price via the shared
    priority+date(+nightly hour) rule), and drop mirrors for products no longer
    in the campaign."""
    from app.models.catalog_product import CatalogProduct
    from app.models.catalog_product_special import CatalogProductSpecial, resolve_active_special
    from app.services.ecommerce.ecommerce_item_service import EcommerceItemService

    slugs = {deal.product_slug for section in campaign.sections for deal in section.deals}
    products = (
        db.query(CatalogProduct).filter(CatalogProduct.slug.in_(slugs)).all() if slugs else []
    )
    product_by_slug = {p.slug: p for p in products}

    existing = (
        db.query(CatalogProductSpecial)
        .filter(CatalogProductSpecial.happy_hour_campaign_id == campaign.id)
        .all()
    )
    existing_by_product_id = {row.product_id: row for row in existing}

    seen_product_ids: set[str] = set()
    touched: list[CatalogProduct] = []
    for section in campaign.sections:
        for deal in section.deals:
            # A disabled deal (manually toggled off, or auto-disabled once its
            # quota sold out) stops applying its price — falls through to the
            # existing-mirror cleanup below, same as a removed product, but
            # the deal itself stays in the section for the admin to see/re-enable.
            if not deal.enabled:
                continue
            product = product_by_slug.get(deal.product_slug)
            if not product:
                continue
            # An offer that is not below the product's own price lowers nothing: no special price (it would raise the price).
            if not (0 < float(deal.offer_price) < float(product.price)):
                continue
            seen_product_ids.add(product.id)
            row = existing_by_product_id.get(product.id)
            if row is None:
                row = CatalogProductSpecial(
                    company_id=product.company_id,
                    product_id=product.id,
                    happy_hour_campaign_id=campaign.id,
                )
                db.add(row)
            row.priority = deal.priority
            row.price = deal.offer_price
            row.date_start = campaign.starts_at
            row.date_end = campaign.ends_at
            row.daily_start_hour = campaign.daily_start_hour
            row.daily_end_hour = campaign.daily_end_hour
            row.quantity = deal.quantity
            row.sort_order = deal.sort_order
            touched.append(product)

    for product_id, row in existing_by_product_id.items():
        if product_id not in seen_product_ids:
            db.delete(row)
            product = db.get(CatalogProduct, product_id)
            if product:
                touched.append(product)

    db.flush()
    # dedupe — a product only ever lands in one of the two loops above, but stay safe
    seen_touched: set[str] = set()
    for product in touched:
        if product.id in seen_touched:
            continue
        seen_touched.add(product.id)
        # The PDP countdown reads catalog_products.sale_ends_at, same as the
        # manual Special Price path — keep it in step with whichever special
        # (Happy Hour or manual) is currently winning for this product.
        all_specials = (
            db.query(CatalogProductSpecial)
            .filter(CatalogProductSpecial.product_id == product.id)
            .all()
        )
        active = resolve_active_special(all_specials)
        product.sale_ends_at = active.date_end if active else None
        EcommerceItemService(db).sync_content_from_catalog(product, mirror_publish=False)
    db.flush()


def _load(db: Session, campaign_id: str) -> MarketingHappyHour | None:
    return (
        db.query(MarketingHappyHour)
        .options(
            joinedload(MarketingHappyHour.sections).joinedload(MarketingHappyHourSection.deals)
        )
        .filter(MarketingHappyHour.id == campaign_id)
        .first()
    )


@router.get("", response_model=HappyHourListResponse)
def list_happy_hours(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HappyHourListResponse:
    q = db.query(MarketingHappyHour).options(
        joinedload(MarketingHappyHour.sections).joinedload(MarketingHappyHourSection.deals)
    )
    if status and status != "all":
        q = q.filter(MarketingHappyHour.status == status)
    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(
            (MarketingHappyHour.title.ilike(term))
            | (MarketingHappyHour.slug.ilike(term))
            | (MarketingHappyHour.description.ilike(term))
        )
    rows = q.order_by(MarketingHappyHour.sort_order.asc(), MarketingHappyHour.updated_at.desc()).all()
    return HappyHourListResponse(
        data=[_to_read(db, row) for row in rows],
        meta=HappyHourListMeta(count=len(rows)),
    )


@router.get("/{campaign_id}", response_model=HappyHourResponse)
def get_happy_hour(campaign_id: str, db: Session = Depends(get_db)) -> HappyHourResponse:
    row = _load(db, campaign_id)
    if not row:
        raise HTTPException(status_code=404, detail="Happy Hour not found")
    return HappyHourResponse(data=_to_read(db, row))


@router.post("", response_model=HappyHourResponse, status_code=201)
def create_happy_hour(
    payload: HappyHourCreate,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> HappyHourResponse:
    slug = payload.slug.strip().strip("/")
    if db.query(MarketingHappyHour).filter(MarketingHappyHour.slug == slug).first():
        raise HTTPException(status_code=400, detail="Slug already exists")
    if payload.ends_at < payload.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    row = MarketingHappyHour(
        slug=slug,
        title=payload.title.strip(),
        subtitle=(payload.subtitle or "").strip() or None,
        description=payload.description or "",
        outlet_label=payload.outlet_label.strip() or "Online Only",
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        daily_start_hour=payload.daily_start_hour,
        daily_end_hour=payload.daily_end_hour,
        status=payload.status,
        terms_json=json.dumps([t.strip() for t in payload.terms if t.strip()], ensure_ascii=False),
        sort_order=payload.sort_order,
    )
    db.add(row)
    db.flush()
    _replace_sections(db, row, payload.sections)
    _sync_specials_for_campaign(db, row)
    db.commit()
    loaded = _load(db, row.id)
    assert loaded
    return HappyHourResponse(data=_to_read(db, loaded))


@router.patch("/{campaign_id}", response_model=HappyHourResponse)
def update_happy_hour(
    campaign_id: str,
    payload: HappyHourUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> HappyHourResponse:
    row = _load(db, campaign_id)
    if not row:
        raise HTTPException(status_code=404, detail="Happy Hour not found")
    data = payload.model_dump(exclude_unset=True)
    sections = data.pop("sections", None)
    terms = data.pop("terms", None)
    if "slug" in data and data["slug"] is not None:
        slug = str(data["slug"]).strip().strip("/")
        clash = (
            db.query(MarketingHappyHour)
            .filter(MarketingHappyHour.slug == slug, MarketingHappyHour.id != campaign_id)
            .first()
        )
        if clash:
            raise HTTPException(status_code=400, detail="Slug already exists")
        data["slug"] = slug
    if "title" in data and data["title"] is not None:
        data["title"] = str(data["title"]).strip()
    if "subtitle" in data:
        sub = (data["subtitle"] or "").strip() if data["subtitle"] is not None else None
        data["subtitle"] = sub or None
    if "outlet_label" in data and data["outlet_label"] is not None:
        data["outlet_label"] = str(data["outlet_label"]).strip() or "Online Only"
    for key, value in data.items():
        setattr(row, key, value)
    if terms is not None:
        row.terms_json = json.dumps([str(t).strip() for t in terms if str(t).strip()], ensure_ascii=False)
    starts = row.starts_at
    ends = row.ends_at
    if ends < starts:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")
    if sections is not None:
        parsed = [HappyHourSectionInput.model_validate(s) for s in sections]
        _replace_sections(db, row, parsed)
    _sync_specials_for_campaign(db, row)
    db.commit()
    loaded = _load(db, campaign_id)
    assert loaded
    return HappyHourResponse(data=_to_read(db, loaded))


@router.delete("/{campaign_id}", status_code=204)
def delete_happy_hour(
    campaign_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> None:
    row = db.query(MarketingHappyHour).filter(MarketingHappyHour.id == campaign_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Happy Hour not found")

    from app.models.catalog_product import CatalogProduct
    from app.models.catalog_product_special import CatalogProductSpecial, resolve_active_special
    from app.services.ecommerce.ecommerce_item_service import EcommerceItemService

    linked_product_ids = [
        r.product_id
        for r in db.query(CatalogProductSpecial)
        .filter(CatalogProductSpecial.happy_hour_campaign_id == campaign_id)
        .all()
    ]
    db.delete(row)  # FK cascade removes the mirrored specials too
    db.commit()
    if linked_product_ids:
        products = db.query(CatalogProduct).filter(CatalogProduct.id.in_(linked_product_ids)).all()
        for product in products:
            # Re-check remaining specials (e.g. a manual one) now that the
            # campaign's mirrors are gone, same as the campaign-save sync.
            remaining = (
                db.query(CatalogProductSpecial)
                .filter(CatalogProductSpecial.product_id == product.id)
                .all()
            )
            active = resolve_active_special(remaining)
            product.sale_ends_at = active.date_end if active else None
            EcommerceItemService(db).sync_content_from_catalog(product, mirror_publish=False)
        db.commit()
