from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MarketingPopup(Base):
    """A storefront popup: a Happy Hour / Offer card, a text notice, or a picture with a link."""

    __tablename__ = "marketing_popups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # happy_hour | offer | notice | image
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="notice")
    # draft | active | disabled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    button_label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    link_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # the Happy Hour / Offer campaign slug (kinds happy_hour / offer)
    campaign_slug: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # session = once per browser session | days = once every `frequency_days` | always = every page view
    frequency: Mapped[str] = mapped_column(String(12), nullable=False, default="session")
    frequency_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # home = the home page only | all = every page | paths = the pages listed in paths_json
    pages: Mapped[str] = mapped_column(String(12), nullable=False, default="home")
    paths_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # all | desktop | mobile
    devices: Mapped[str] = mapped_column(String(10), nullable=False, default="all")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
