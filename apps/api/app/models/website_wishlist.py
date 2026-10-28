"""Storefront wishlist — website_* tables in the shared AgainERP database."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, engine

# A shopper has one list of each kind: the wishlist, and "saved" (save for later).
WISHLIST_KINDS = ("wishlist", "saved")


class WebsiteWishlist(Base):
    __tablename__ = "website_wishlists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    wishlist_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    customer_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("commerce_customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="wishlist", server_default="wishlist", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    items: Mapped[list["WebsiteWishlistItem"]] = relationship(
        "WebsiteWishlistItem",
        back_populates="wishlist",
        cascade="all, delete-orphan",
        order_by="WebsiteWishlistItem.created_at.desc()",
    )


class WebsiteWishlistItem(Base):
    __tablename__ = "website_wishlist_items"
    __table_args__ = (
        UniqueConstraint("wishlist_id", "product_id", name="uq_website_wishlist_product"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    wishlist_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("website_wishlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    item_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    thumbnail: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    compare_at_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    wishlist: Mapped["WebsiteWishlist"] = relationship("WebsiteWishlist", back_populates="items")


def ensure_website_wishlist_columns() -> None:
    """Add website_wishlists.kind on existing DBs (no Alembic in this repo)."""
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE website_wishlists ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'wishlist'")
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_website_wishlists_kind ON website_wishlists (kind)"))
