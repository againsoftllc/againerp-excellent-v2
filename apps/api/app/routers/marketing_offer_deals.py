"""One flat list of every deal of every Offer and Happy Hour campaign (the "Offer Products" admin grid):
which offers a product is in, and edit a deal in place (price, priority, quota, on/off) or move it to another campaign.
Every write re-runs the campaign's special-price sync, so the storefront/cart see the change at once."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps.auth import require_write_access
from app.models.catalog_product import CatalogProduct
from app.models.catalog_product_special import CatalogProductSpecial, resolve_active_special
from app.models.marketing_happy_hour import MarketingHappyHour, MarketingHappyHourDeal, MarketingHappyHourSection
from app.models.marketing_offer import MarketingOffer, MarketingOfferDeal, MarketingOfferSection

router = APIRouter(prefix="/marketing/offer-deals", tags=["marketing-offer-deals"])

Kind = Literal["offer", "happy_hour"]


def _models(kind: str):
    if kind == "offer":
        return MarketingOffer, MarketingOfferSection, MarketingOfferDeal, "offer_id", MarketingOffer.sections
    if kind == "happy_hour":
        return MarketingHappyHour, MarketingHappyHourSection, MarketingHappyHourDeal, "campaign_id", MarketingHappyHour.sections
    raise HTTPException(status_code=400, detail="kind must be offer or happy_hour")


def _load_campaign(db: Session, kind: str, campaign_id: str):
    camp, sec, deal, _fk, rel = _models(kind)
    row = db.query(camp).options(joinedload(rel).joinedload(sec.deals)).filter(camp.id == campaign_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return row


def _sync(db: Session, kind: str, campaign) -> None:
    if kind == "offer":
        from app.routers.marketing_offers import _sync_specials_for_offer

        _sync_specials_for_offer(db, campaign)
    else:
        from app.routers.marketing_happy_hours import _sync_specials_for_campaign

        _sync_specials_for_campaign(db, campaign)


def _special_key(kind: str):
    return CatalogProductSpecial.offer_campaign_id if kind == "offer" else CatalogProductSpecial.happy_hour_campaign_id


class DealPatch(BaseModel):
    offer_price: Optional[float] = None
    priority: Optional[int] = None
    quantity: Optional[int] = None  # null clears the quota (unlimited)
    enabled: Optional[bool] = None
    note: Optional[str] = None
    move_to_kind: Optional[Kind] = None
    move_to_campaign_id: Optional[str] = None
    move_to_section_id: Optional[str] = None  # which section of the target offer (empty = its first section)


class BulkBody(BaseModel):
    ids: list[str]  # "offer:<deal id>" / "happy_hour:<deal id>"
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    discount_percent: Optional[float] = None  # offer price = regular price less this %
    move_to_kind: Optional[Kind] = None
    move_to_campaign_id: Optional[str] = None
    move_to_section_id: Optional[str] = None
    delete: bool = False


def _find_deal(db: Session, kind: str, deal_id: str):
    camp, sec, deal, fk, _rel = _models(kind)
    d = db.query(deal).filter(deal.id == deal_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Deal not found")
    s = db.query(sec).filter(sec.id == d.section_id).first()
    return d, s, getattr(s, fk)


def _move(db: Session, kind: str, d, from_camp_id: str, to_kind: str, to_id: str, to_section_id: Optional[str] = None):
    """Take the deal out of its campaign and add it (same price/priority/quota/on-off) to a section of another one - the section
    the admin picked, else the target's first. The same campaign is a valid target when the deal goes to another of its sections."""
    same_campaign = to_kind == kind and to_id == from_camp_id
    if same_campaign and not to_section_id:
        return None
    target = _load_campaign(db, to_kind, to_id)
    if to_kind == "offer" and (getattr(target, "page_mode", "auto") == "custom" or getattr(target, "custom_link", None)):
        raise HTTPException(status_code=422, detail=f"“{target.title}” is a custom page offer: it has no products")
    _c, sec, deal, fk, _rel = _models(to_kind)
    if any(x.product_slug == d.product_slug and x.id != d.id for s in target.sections for x in s.deals):
        raise HTTPException(status_code=409, detail=f"{d.product_slug} is already in “{target.title}”")
    section = None
    if to_section_id:
        section = next((s for s in target.sections if s.id == to_section_id), None)
        if section is None:
            raise HTTPException(status_code=422, detail=f"That section is not in “{target.title}”")
        if same_campaign and section.id == d.section_id:
            return None  # already there
    else:
        section = target.sections[0] if target.sections else None
    if section is None:
        section = sec(**{fk: target.id}, key="deals", label="Deals", sort_order=0)
        db.add(section)
        db.flush()
    n = len(section.deals)
    new = deal(section_id=section.id, product_slug=d.product_slug, offer_price=d.offer_price, note=d.note,
               priority=d.priority, quantity=d.quantity, enabled=d.enabled, sort_order=n)
    db.add(new)
    db.delete(d)
    db.flush()
    db.expire(target)
    return target


def _utc_iso(dt):
    return dt.isoformat() if dt else None


@router.get("")
def list_offer_deals(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    specials = db.query(CatalogProductSpecial).all()
    by_product: dict[str, list[CatalogProductSpecial]] = {}
    by_camp: dict[tuple[str, str], CatalogProductSpecial] = {}
    for sp in specials:
        by_product.setdefault(sp.product_id, []).append(sp)
        if sp.offer_campaign_id:
            by_camp[("offer:" + sp.offer_campaign_id, sp.product_id)] = sp
        if sp.happy_hour_campaign_id:
            by_camp[("happy_hour:" + sp.happy_hour_campaign_id, sp.product_id)] = sp
    winner_by_product = {pid: resolve_active_special(lst) for pid, lst in by_product.items()}

    products = {p.slug: p for p in db.query(CatalogProduct).all()}
    for kind in ("offer", "happy_hour"):
        camp, sec, deal, _fk, rel = _models(kind)
        for c in db.query(camp).options(joinedload(rel).joinedload(sec.deals)).all():
            for s in c.sections:
                for d in s.deals:
                    p = products.get(d.product_slug)
                    sp = by_camp.get((f"{kind}:{c.id}", p.id)) if p else None
                    win = winner_by_product.get(p.id) if p else None
                    rows.append({
                        "key": f"{kind}:{d.id}",
                        "kind": kind,
                        "deal_id": d.id,
                        "campaign_id": c.id,
                        "campaign_title": c.title,
                        "campaign_slug": c.slug,
                        "campaign_status": c.status,
                        "starts_at": _utc_iso(c.starts_at),
                        "ends_at": _utc_iso(c.ends_at),
                        "daily_start_hour": c.daily_start_hour,
                        "daily_end_hour": c.daily_end_hour,
                        "section": s.label,
                        "section_id": s.id,
                        "product_slug": d.product_slug,
                        "product_id": p.id if p else None,
                        "product_name": p.name if p else d.product_slug,
                        "sku": p.sku if p else None,
                        "model": (p.model or None) if p else None,
                        "thumbnail": p.thumbnail if p else None,
                        "brand": p.brand if p else None,
                        "category": p.category if p else None,
                        "product_status": p.status if p else "missing",
                        "regular_price": float(p.price) if p else None,
                        "offer_price": float(d.offer_price),
                        "priority": d.priority,
                        "quantity": d.quantity,
                        "quantity_sold": int(sp.quantity_sold or 0) if sp else 0,
                        "enabled": bool(d.enabled),
                        "note": d.note,
                        # live: its price applies this very minute; winner: and it beats the product's other live offers
                        "live": bool(sp and resolve_active_special([sp]) is not None),
                        "winner": bool(sp and win is not None and win.id == sp.id),
                    })
    return {"data": rows, "meta": {"count": len(rows)}}


@router.patch("/{kind}/{deal_id}")
def update_offer_deal(kind: Kind, deal_id: str, body: DealPatch, db: Session = Depends(get_db), _: object = Depends(require_write_access)) -> dict[str, Any]:
    d, _s, camp_id = _find_deal(db, kind, deal_id)
    fields = body.model_fields_set
    if "offer_price" in fields and body.offer_price is not None:
        if body.offer_price <= 0:
            raise HTTPException(status_code=422, detail="Offer price must be above 0")
        d.offer_price = body.offer_price
    if "priority" in fields and body.priority is not None:
        d.priority = body.priority
    if "quantity" in fields:
        if body.quantity is not None and body.quantity < 0:
            raise HTTPException(status_code=422, detail="Quantity can't be negative")
        d.quantity = body.quantity
    if "enabled" in fields and body.enabled is not None:
        d.enabled = body.enabled
    if "note" in fields:
        d.note = (body.note or None)
    db.flush()
    campaigns = [(kind, camp_id)]
    if body.move_to_campaign_id:
        target = _move(db, kind, d, camp_id, body.move_to_kind or kind, body.move_to_campaign_id, body.move_to_section_id)
        if target is not None and (body.move_to_kind or kind, body.move_to_campaign_id) not in campaigns:
            campaigns.append((body.move_to_kind or kind, body.move_to_campaign_id))
    for k, cid in campaigns:
        db.expire_all()
        _sync(db, k, _load_campaign(db, k, cid))
    db.commit()
    return {"ok": True}


@router.delete("/{kind}/{deal_id}", status_code=204)
def delete_offer_deal(kind: Kind, deal_id: str, db: Session = Depends(get_db), _: object = Depends(require_write_access)) -> None:
    d, _s, camp_id = _find_deal(db, kind, deal_id)
    db.delete(d)
    db.flush()
    db.expire_all()
    _sync(db, kind, _load_campaign(db, kind, camp_id))
    db.commit()


@router.post("/bulk")
def bulk_offer_deals(body: BulkBody, db: Session = Depends(get_db), _: object = Depends(require_write_access)) -> dict[str, Any]:
    touched: set[tuple[str, str]] = set()
    errors: list[str] = []
    done = 0
    for key in body.ids:
        try:
            kind, _, deal_id = key.partition(":")
            d, _s, camp_id = _find_deal(db, kind, deal_id)
            touched.add((kind, camp_id))
            if body.delete:
                db.delete(d)
            else:
                if body.enabled is not None:
                    d.enabled = body.enabled
                if body.priority is not None:
                    d.priority = body.priority
                if body.discount_percent is not None:
                    p = db.query(CatalogProduct).filter(CatalogProduct.slug == d.product_slug).first()
                    if p and 0 <= body.discount_percent < 100:
                        d.offer_price = round(float(p.price) * (1 - body.discount_percent / 100), 2)
                if body.move_to_campaign_id:
                    tk = body.move_to_kind or kind
                    _move(db, kind, d, camp_id, tk, body.move_to_campaign_id, body.move_to_section_id)
                    touched.add((tk, body.move_to_campaign_id))
            db.flush()
            done += 1
        except HTTPException as e:
            errors.append(f"{key}: {e.detail}")
    for k, cid in touched:
        db.expire_all()
        _sync(db, k, _load_campaign(db, k, cid))
    db.commit()
    return {"ok": True, "done": done, "errors": errors}
