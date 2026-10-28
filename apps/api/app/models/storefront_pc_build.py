"""Storefront PC Builder — a build the shopper saved or shared (slot → product slug)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StorefrontPcBuild(Base):
    __tablename__ = "storefront_pc_builds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    build_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    # Null for a guest's shared link; set when a signed-in customer saves it.
    customer_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("commerce_customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="My PC Build")
    # [{"slot": "cpu", "slug": "amd-ryzen-7-7700-processor"}, ...]
    items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
