from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MarketingOffer(Base):
    """Time-boxed offer campaign (hand-picked products + campaign prices) —
    same shape as MarketingHappyHour, minus the mandatory nightly window and
    plus a card image. See app/models/marketing_happy_hour.py for the sibling
    this was mirrored from."""

    __tablename__ = "marketing_offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subtitle: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # When set, this offer skips its own product-grid page entirely: the
    # Offers list card's "View Details" AND the offer's own detail URL both
    # redirect here instead. Sections become optional in that case.
    custom_link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    outlet_label: Mapped[str] = mapped_column(String(120), nullable=False, default="All Outlet")
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Optional nightly window — null on both means "active all day" within
    # the date range above. Same semantics as CatalogProductSpecial's.
    daily_start_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    daily_end_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    terms_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    sections: Mapped[list["MarketingOfferSection"]] = relationship(
        "MarketingOfferSection",
        back_populates="offer",
        cascade="all, delete-orphan",
        order_by="MarketingOfferSection.sort_order",
    )


class MarketingOfferSection(Base):
    __tablename__ = "marketing_offer_sections"
    __table_args__ = (UniqueConstraint("offer_id", "key", name="uq_marketing_offer_section_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    offer_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("marketing_offers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    offer: Mapped["MarketingOffer"] = relationship("MarketingOffer", back_populates="sections")
    deals: Mapped[list["MarketingOfferDeal"]] = relationship(
        "MarketingOfferDeal",
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="MarketingOfferDeal.sort_order",
    )


class MarketingOfferDeal(Base):
    __tablename__ = "marketing_offer_deals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    section_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("marketing_offer_sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    offer_price: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # See MarketingHappyHourDeal.quantity / .enabled — same deal-quota +
    # auto-disable-on-sellout behavior, mirrored here.
    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    section: Mapped["MarketingOfferSection"] = relationship(
        "MarketingOfferSection", back_populates="deals"
    )
