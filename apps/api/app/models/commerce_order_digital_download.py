from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CommerceOrderDigitalDownload(Base):
    """One secure download grant for one digital file on one paid order.

    Created once the order's payment is confirmed (see
    app/services/ecommerce/digital_delivery_service.py). `max_downloads` and
    `expires_at` are snapshotted from the product's digital file settings at
    grant time, so a later change to the product doesn't retroactively alter
    a link already emailed to a customer.
    """

    __tablename__ = "commerce_order_digital_downloads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("commerce_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("commerce_order_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    digital_file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("catalog_product_digital_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_downloads: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
