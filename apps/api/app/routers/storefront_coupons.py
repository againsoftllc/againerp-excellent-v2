"""Public storefront coupons authored in Website → Marketing → Coupons."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.catalog_brand import CatalogBrand
from app.models.catalog_category import CatalogCategory
from app.models.ecommerce_item import EcommerceItem
from app.models.marketing_coupon import MarketingCoupon
from app.routers.marketing_coupons import OPEN_END, OPEN_START

router = APIRouter(prefix="/coupons", tags=["storefront-coupons"])
STOREFRONT_CACHE = "public, max-age=30, s-maxage=60, stale-while-revalidate=120"


def _set_cache(response: Response) -> None:
    response.headers["Cache-Control"] = STOREFRONT_CACHE


def _iso_date(value: date | datetime | None, sentinel: date | None = None) -> str:
    if value is None:
        return ""
    if sentinel is not None and value == sentinel:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _iso_dt(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _expand_product_slugs(db: Session, rules: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for slug in rules.get("productSlugs") or []:
        s = str(slug).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    if rules.get("appliesToAll"):
        return out
    cat_slugs = [str(s) for s in (rules.get("categorySlugs") or []) if s]
    brand_slugs = [str(s) for s in (rules.get("brandSlugs") or []) if s]
    filters = []
    if cat_slugs:
        cat_ids = [
            row.id
            for row in db.query(CatalogCategory).filter(CatalogCategory.slug.in_(cat_slugs)).all()
        ]
        if cat_ids:
            filters.append(EcommerceItem.primary_category_id.in_(cat_ids))
    if brand_slugs:
        brand_ids = [
            row.id for row in db.query(CatalogBrand).filter(CatalogBrand.slug.in_(brand_slugs)).all()
        ]
        if brand_ids:
            filters.append(EcommerceItem.brand_id.in_(brand_ids))
    if not filters:
        return out
    extra = (
        db.query(EcommerceItem.slug)
        .filter(or_(*filters))
        .limit(2000)
        .all()
    )
    for (slug,) in extra:
        s = str(slug or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _public_coupon(db: Session, row: MarketingCoupon) -> dict[str, Any]:
    rules = dict(getattr(row, "rules_json", None) or {})
    kind = "price-range" if rules.get("kind") == "price-range" else "product"
    dtype = "percent" if (row.discount_type or "").lower() in {"percent", "percentage"} else "flat"
    product_slugs = _expand_product_slugs(db, rules) if kind == "product" else []
    return {
        "id": row.id,
        "kind": kind,
        "code": row.code,
        "label": rules.get("label") or row.name or "",
        "type": dtype,
        "value": float(row.discount_value or 0),
        "maxDiscount": _num(rules.get("maxDiscount")),
        "minOrder": _num(row.min_order_amount),
        "startsAt": _iso_date(row.starts_at, OPEN_START),
        "endsAt": _iso_date(row.ends_at, OPEN_END),
        "usageLimit": row.redemption_limit,
        "used": row.redemptions or 0,
        "active": row.status in {"active", "scheduled"},
        # Empty rules used to mean “every product”, so seed codes like VIP20
        # appeared on cards that were never assigned a coupon. Blanket coverage
        # is only when admin checks appliesToAll.
        "appliesToAll": bool(rules.get("appliesToAll")) if kind == "product" else False,
        "categorySlugs": list(rules.get("categorySlugs") or []) if kind == "product" else [],
        "brandSlugs": list(rules.get("brandSlugs") or []) if kind == "product" else [],
        "productSlugs": product_slugs,
        "minLineTotal": _num(rules.get("minLineTotal")),
        "maxLineTotal": _num(rules.get("maxLineTotal")),
        "createdAt": _iso_dt(row.created_at),
        "updatedAt": _iso_dt(row.updated_at),
    }


class StorefrontCouponDB(BaseModel):
    coupons: Dict[str, dict] = {}


class StorefrontCouponListResponse(BaseModel):
    data: StorefrontCouponDB


@router.get("", response_model=StorefrontCouponListResponse)
def list_storefront_coupons(
    response: Response,
    db: Session = Depends(get_db),
) -> StorefrontCouponListResponse:
    _set_cache(response)
    rows = (
        db.query(MarketingCoupon)
        .filter(MarketingCoupon.status.in_(["active", "scheduled"]))
        .order_by(MarketingCoupon.updated_at.desc())
        .all()
    )
    coupons: Dict[str, dict] = {}
    for row in rows:
        payload = _public_coupon(db, row)
        coupons[payload["id"]] = payload
    return StorefrontCouponListResponse(data=StorefrontCouponDB(coupons=coupons))
