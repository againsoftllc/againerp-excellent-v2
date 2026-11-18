from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, event, func, inspect, text
from sqlalchemy.orm import Mapped, mapped_column, object_session

from app.database import Base


class CatalogProductVariant(Base):
    __tablename__ = "catalog_product_variants"
    gallery_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    product_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("catalog_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Default")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    purchase_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("media.id", ondelete="SET NULL"), nullable=True)
    # Elim / external variation data
    options_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # The manufacturer part number this variant uses (one of the product's mpns_json).
    mpn: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    external_sku_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def _product_sku(connection, product_id: str):
    row = connection.execute(text("select sku from catalog_products where id = :i"), {"i": product_id}).first()
    return row[0] if row and row[0] else None


@event.listens_for(CatalogProductVariant, "before_insert")
def _give_new_variant_its_code(mapper, connection, target) -> None:
    """A variant's SKU is the product's code plus a number (EX000123-1, EX000123-2 ...), never its name. The plain default variant of a
    product with no options shares the product's own code."""
    base = _product_sku(connection, target.product_id)
    if not base or (target.sku or "") == base:
        return
    session = object_session(target)
    cache = session.info.setdefault("_variant_code_next", {}) if session is not None else {}
    n = cache.get(target.product_id)
    if n is None:
        top = connection.execute(
            text(
                "select coalesce(max(cast(substring(sku from '-([0-9]+)$') as integer)), 0) "
                "from catalog_product_variants where product_id = :p and sku like :like"
            ),
            {"p": target.product_id, "like": base + "-%"},
        ).scalar_one()
        n = int(top) + 1
    while connection.execute(text("select 1 from catalog_product_variants where sku = :s"), {"s": f"{base}-{n}"}).first():
        n += 1
    target.sku = f"{base}-{n}"
    cache[target.product_id] = n + 1


@event.listens_for(CatalogProductVariant, "before_update")
def _variant_sku_never_changes(mapper, connection, target) -> None:
    """Fixed once given. The one allowed change is to the product's own code (a product whose last option was removed is plain again)."""
    history = inspect(target).attrs.sku.history
    if history.has_changes() and history.deleted:
        if target.sku != _product_sku(connection, target.product_id):
            target.sku = history.deleted[0]
