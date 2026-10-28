"""Resolve marketing_coupons discounts for storefront cart/checkout."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.models.catalog_brand import CatalogBrand
from app.models.catalog_category import CatalogCategory
from app.models.ecommerce_item import EcommerceItem
from app.models.marketing_coupon import MarketingCoupon


class CouponError(ValueError):
    pass


@dataclass(frozen=True)
class CouponDiscount:
    code: str
    amount: Decimal
    label: str
    discount_type: str


@dataclass(frozen=True)
class CouponCartLine:
    slug: str
    unit_price: Decimal
    quantity: int


def _normalize(code: str) -> str:
    return code.strip().upper()


def _rules(row: MarketingCoupon) -> dict:
    return dict(getattr(row, "rules_json", None) or {})


def _money(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def find_active_coupon(db: Session, code: str) -> MarketingCoupon:
    normalized = _normalize(code)
    if not normalized:
        raise CouponError("Please enter a promo code")

    row = db.query(MarketingCoupon).filter(MarketingCoupon.code == normalized).first()
    if not row:
        raise CouponError("Please enter a valid promo code")

    today = date.today()
    if row.status not in {"active", "scheduled"}:
        raise CouponError("This promo code is not active")
    if row.starts_at and today < row.starts_at:
        raise CouponError("This promo code is not active yet")
    if row.ends_at and today > row.ends_at:
        raise CouponError("This promo code has expired")
    if row.redemption_limit is not None and row.redemptions >= row.redemption_limit:
        raise CouponError("This promo code has reached its redemption limit")

    return row


def _has_explicit_product_scope(rules: dict) -> bool:
    if rules.get("appliesToAll"):
        return False
    return bool(rules.get("productSlugs") or rules.get("categorySlugs") or rules.get("brandSlugs"))


def coupon_covers_slug(db: Session, row: MarketingCoupon, slug: str) -> bool:
    rules = _rules(row)
    kind = rules.get("kind") or "product"
    if kind != "product":
        return False
    if rules.get("appliesToAll"):
        return True
    if not rules:
        return False
    products = {str(s) for s in (rules.get("productSlugs") or []) if s}
    if slug in products:
        return True
    cats = {str(s) for s in (rules.get("categorySlugs") or []) if s}
    brands = {str(s) for s in (rules.get("brandSlugs") or []) if s}
    if not cats and not brands:
        return False
    item = db.query(EcommerceItem).filter(EcommerceItem.slug == slug).first()
    if not item:
        return False
    if cats and item.primary_category_id:
        cat = db.get(CatalogCategory, item.primary_category_id)
        if cat and cat.slug in cats:
            return True
    if brands and item.brand_id:
        brand = db.get(CatalogBrand, item.brand_id)
        if brand and brand.slug in brands:
            return True
    return False


def _slug_has_product_offer(db: Session, slug: str) -> bool:
    today = date.today()
    rows = (
        db.query(MarketingCoupon)
        .filter(MarketingCoupon.status.in_(["active", "scheduled"]))
        .all()
    )
    for other in rows:
        rules = _rules(other)
        if (rules.get("kind") or "product") != "product":
            continue
        if not _has_explicit_product_scope(rules):
            continue
        if other.starts_at and today < other.starts_at:
            continue
        if other.ends_at and today > other.ends_at:
            continue
        if coupon_covers_slug(db, other, slug):
            return True
    return False


def _discount_amount(row: MarketingCoupon, amount: Decimal, units: int) -> Decimal:
    if amount <= 0:
        return Decimal("0")
    dtype = (row.discount_type or "percent").strip().lower()
    rules = _rules(row)
    if dtype in {"percent", "percentage"}:
        raw = (amount * (row.discount_value / Decimal("100"))).quantize(Decimal("0.01"))
    else:
        raw = (Decimal(row.discount_value) * Decimal(units)).quantize(Decimal("0.01"))
    cap = _money(rules.get("maxDiscount"))
    if cap > 0:
        raw = min(raw, cap)
    return max(Decimal("0"), min(raw, amount))


def calculate_coupon_discount(
    db: Session,
    row: MarketingCoupon,
    subtotal: Decimal,
    lines: Sequence[CouponCartLine] | None = None,
) -> CouponDiscount:
    if subtotal <= 0:
        raise CouponError("Add items to your cart before applying a promo code")

    if row.min_order_amount is not None and subtotal < row.min_order_amount:
        raise CouponError(f"Minimum order amount is ৳{row.min_order_amount}")

    rules = _rules(row)
    kind = rules.get("kind") or "product"
    dtype = (row.discount_type or "percent").strip().lower()
    cart_lines = list(lines or [])

    applies_all = bool(rules.get("appliesToAll"))

    if kind == "price-range":
        open_lines = [
            line
            for line in cart_lines
            if not _slug_has_product_offer(db, line.slug)
        ]
        pooled = sum((line.unit_price * line.quantity for line in open_lines), Decimal("0"))
        min_line = _money(rules.get("minLineTotal"))
        max_line = _money(rules.get("maxLineTotal"))
        if min_line > 0 and pooled < min_line:
            raise CouponError("This promo code does not apply to this cart total")
        if max_line > 0 and pooled > max_line:
            raise CouponError("This promo code does not apply to this cart total")
        amount = _discount_amount(row, pooled, 1)
    else:
        if cart_lines and not applies_all:
            eligible = [line for line in cart_lines if coupon_covers_slug(db, row, line.slug)]
            covered = sum((line.unit_price * line.quantity for line in eligible), Decimal("0"))
            units = sum((line.quantity for line in eligible), 0)
            amount = _discount_amount(row, covered, units)
        else:
            amount = _discount_amount(row, subtotal, 1)

    if amount <= 0:
        raise CouponError("This promo code has no discount for this cart")

    return CouponDiscount(
        code=row.code,
        amount=amount,
        label=row.discount_label or row.name,
        discount_type=dtype,
    )


def resolve_coupon_discount(
    db: Session,
    coupon_code: Optional[str],
    subtotal: Decimal,
    lines: Sequence[CouponCartLine] | None = None,
) -> Optional[CouponDiscount]:
    if not coupon_code or not coupon_code.strip():
        return None
    row = find_active_coupon(db, coupon_code)
    return calculate_coupon_discount(db, row, subtotal, lines)


def record_coupon_redemption(db: Session, code: str) -> None:
    """Bump the usage counter an order actually placed with.

    Called once per placed order, never on preview/apply, so a coupon's
    redemption_limit (checked in find_active_coupon) reflects real orders.
    """
    row = db.query(MarketingCoupon).filter(MarketingCoupon.code == _normalize(code)).first()
    if row:
        row.redemptions = (row.redemptions or 0) + 1
