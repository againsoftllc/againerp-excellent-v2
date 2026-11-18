from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Sequence, String, Text, event, func, inspect, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# A product's serial number (1, 2, 3 ...) and its code (EX000001, EX000002 ...). The code IS the product's SKU and is the same in the
# Product ID column; the UUID stays inside as the key the other tables point at. Numbers are never given out twice (a database sequence).
PRODUCT_CODE_PREFIX = "EX"
PRODUCT_CODE_WIDTH = 6
catalog_product_serial_seq = Sequence("catalog_product_serial_seq", metadata=Base.metadata)


def product_code(serial: int) -> str:
    return f"{PRODUCT_CODE_PREFIX}{int(serial):0{PRODUCT_CODE_WIDTH}d}"


class CatalogProduct(Base):
    """
    Catalog commerce extension — merchandising, pricing, taxonomy (ADR-014 P7).

    Identity fields (sku, name, status, product_type) are **deprecated mirrors**
    of `items`. Authoritative identity lives on `items`; this row is keyed by
    `item_id`. API responses resolve identity from items at read time.
    """

    __tablename__ = "catalog_products"
    seo_keyphrase: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sale_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    pre_order_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    item_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # P7 mirror — SSOT: items.name
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)  # P7 mirror
    # 1, 2, 3 ... given when the product is saved (never changes); the SKU is product_code(serial_no)
    serial_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # Internal note / remarks about the product — staff-only, never shown on the storefront.
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    compare_at_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    purchase_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    last_selling_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    track_quantity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    not_for_selling: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weight: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tax_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    tax_type: Mapped[str] = mapped_column(String(20), nullable=False, default="exclusive")
    stock_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")  # P7 mirror — publish via ecommerce_items
    product_type: Mapped[str] = mapped_column(String(20), nullable=False, default="simple")  # P7 mirror — SSOT: items.item_type
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    brand_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("catalog_brands.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("catalog_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    attribute_profile_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("catalog_attribute_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    short_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    seo_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    seo_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    focus_keyphrase: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    warranty: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    origin: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    thumbnail: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    custom_specs_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Variant attribute definitions (name + ordered values + optional per-value image) —
    # persisted separately from custom_specs_json so the Variants tab survives reload.
    variant_attributes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Manufacturer part numbers (MPN) of the product, a JSON list of strings; each variant picks one (variant.mpn).
    mpns_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Combo product composition — list of {product_id, variant_id, product_name, sku,
    # quantity, unit_price, thumbnail}; only meaningful when product_type == "combo".
    combo_components_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Dropship / Elim enrichment (kept outside custom_specs so product-form saves cannot wipe them)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    seller_info_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dropship_meta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Module visibility: a product belongs to the Inventory module's catalog and/or the Website module's product
    # list. Both default true (legacy rows); each module's "create" sets only its own flag, and adding a website
    # product to inventory is an explicit action (POST /catalog/products/add-to-inventory).
    in_inventory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    on_website: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    gallery_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # image URL list (CDN hotlinks)
    video_urls_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    # who made the last change: filled for every save from the signed-in user (app/services/audit_actor.py), the AI chat included
    updated_by_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    updated_by_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


@event.listens_for(CatalogProduct, "before_insert")
def _give_new_product_its_code(mapper, connection, target) -> None:
    """Every new product gets the next serial number and its code as the SKU - whatever SKU the caller (form, import, clone) brought."""
    if target.serial_no is None:
        target.serial_no = int(connection.execute(text("select nextval('catalog_product_serial_seq')")).scalar_one())
    target.sku = product_code(target.serial_no)


@event.listens_for(CatalogProduct, "before_update")
def _product_sku_never_changes(mapper, connection, target) -> None:
    """The SKU is fixed once the product exists: any change made in a flush (an edit, an import, a mirror from items) is put back."""
    history = inspect(target).attrs.sku.history
    if history.has_changes() and history.deleted:
        target.sku = history.deleted[0]
