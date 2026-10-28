from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CatalogStockStatus(Base):
    """Client-definable stock statuses.

    Behaviour is driven by the flags below rather than by matching on the code,
    so a status the client invents ("Damaged", "Discontinued") behaves exactly
    as they configured it instead of silently falling through to "in stock".
    """

    __tablename__ = "catalog_stock_statuses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")

    # Stored on catalog_products.stock_status — never editable after creation.
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # The four originals: label is editable, the row cannot be deleted.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- behaviour ---
    counts_as_in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sellable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tracks_quantity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    needs_end_date: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- storefront presentation ---
    badge_label: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    badge_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    show_in_filter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Default "Call for Price" number for any product on this status that
    # hasn't set its own (catalog_products.contact_phone overrides this).
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(),
    )


# code -> (label, in_stock, sellable, tracks_qty, needs_end_date, badge, colour)
DEFAULT_STOCK_STATUSES: list[dict] = [
    {
        "code": "in_stock", "label": "In Stock", "sort_order": 10,
        "counts_as_in_stock": True, "sellable": True, "tracks_quantity": False,
        "needs_end_date": False, "badge_label": "In Stock", "badge_color": "#00a65a",
    },
    {
        "code": "out_of_stock", "label": "Out of Stock", "sort_order": 20,
        "counts_as_in_stock": False, "sellable": False, "tracks_quantity": False,
        "needs_end_date": False, "badge_label": "Out of Stock", "badge_color": "#d64545",
    },
    {
        "code": "pre_order", "label": "Pre-order", "sort_order": 30,
        "counts_as_in_stock": False, "sellable": True, "tracks_quantity": True,
        "needs_end_date": True, "badge_label": "Pre-order", "badge_color": "#f0932b",
    },
    {
        "code": "coming_soon", "label": "Coming Soon", "sort_order": 40,
        "counts_as_in_stock": False, "sellable": False, "tracks_quantity": False,
        "needs_end_date": False, "badge_label": "Upcoming", "badge_color": "#5b7cfa",
    },
    {
        "code": "call_for_price", "label": "Call for Price", "sort_order": 50,
        "counts_as_in_stock": False, "sellable": False, "tracks_quantity": False,
        "needs_end_date": False, "badge_label": "Call for Price", "badge_color": "#6c757d",
    },
]


def ensure_default_stock_statuses(db) -> int:
    """Idempotent — creates any built-in row that is missing and returns the count."""
    existing = {row.code for row in db.query(CatalogStockStatus.code).all()}
    created = 0
    for spec in DEFAULT_STOCK_STATUSES:
        if spec["code"] in existing:
            continue
        db.add(CatalogStockStatus(is_system=True, is_active=True, show_in_filter=True, **spec))
        created += 1
    if created:
        db.commit()
    return created
