from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductPageBanner(Base):
    """A promo banner (e.g. "Free Home Delivery") shown on the storefront
    product detail page, admin-managed. Several can be active at once, each
    targeting a different slice of the catalog — `target_type` decides which
    of `target_category_ids_json`/`target_product_ids_json` applies."""

    __tablename__ = "product_page_banners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    link_href: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    alt_text: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # "all" | "category" | "product"
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    target_category_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    target_product_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
