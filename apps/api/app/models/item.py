from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, UniqueConstraint, event, func, inspect, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Item(Base):
    """Universal Item Master (SSOT) — identity fields only (ADR-014)."""

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("company_id", "sku", name="uq_items_company_sku"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default", index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    barcode_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="C128")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, default="physical", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
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


@event.listens_for(Item, "before_update")
def _catalog_item_sku_never_changes(mapper, connection, target) -> None:
    """An item behind a catalog product carries the product's code as its SKU: the Items screen can not change it either."""
    history = inspect(target).attrs.sku.history
    if history.has_changes() and history.deleted:
        linked = connection.execute(
            text("select 1 from catalog_products where item_id = :i or id = :i limit 1"), {"i": target.id}
        ).first()
        if linked:
            target.sku = history.deleted[0]
