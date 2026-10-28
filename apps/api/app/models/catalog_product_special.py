from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CatalogProductSpecial(Base):
    """OpenCart-style special prices — a product can hold several, each with its
    own priority and date window. The lowest priority number that is currently
    inside its window wins."""

    __tablename__ = "catalog_product_specials"

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
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    date_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    date_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Nightly window (Dhaka wall-clock hour, 0-24). Null on both = active all day.
    daily_start_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    daily_end_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Deal-quota, independent of the product's physical stock — null means
    # unlimited. Once quantity_sold reaches quantity the deal stops resolving
    # as active (falls back to the next-priority special, or the regular
    # price) even though its date window may still be open.
    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quantity_sold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Set when this row is a synced mirror of a Happy Hour campaign deal — see
    # app/routers/marketing_happy_hours.py `_sync_specials_for_campaign`. Cascades
    # so deleting the campaign cleans up its mirrored specials automatically.
    happy_hour_campaign_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("marketing_happy_hours.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Same idea, mirrored to the Offer module — see
    # app/routers/marketing_offers.py `_sync_specials_for_offer`.
    offer_campaign_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("marketing_offers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """The admin form posts ISO strings ending in "Z", so pydantic hands us
    timezone-aware datetimes while the column (and utcnow) are naive. Fold
    everything to naive UTC so writes and comparisons stay consistent."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


BD_UTC_OFFSET_HOURS = 6  # storefront is Bangladesh-only; daily hours are Dhaka wall-clock


def in_daily_window(moment_utc: datetime, start_hour: Optional[int], end_hour: Optional[int]) -> bool:
    """Is `moment_utc` inside the [start_hour, end_hour) Dhaka wall-clock window?
    Either bound missing means "no nightly restriction" (active all day)."""
    if start_hour is None or end_hour is None:
        return True
    bd_hour = (moment_utc.hour + BD_UTC_OFFSET_HOURS) % 24
    start = start_hour % 24
    if end_hour <= start_hour:
        # wraps past midnight, e.g. 22 -> 6
        return bd_hour >= start or bd_hour < (end_hour % 24)
    return start <= bd_hour < end_hour


def resolve_active_special(
    specials: list["CatalogProductSpecial"],
    *,
    now: Optional[datetime] = None,
) -> Optional["CatalogProductSpecial"]:
    """OpenCart rule: among specials whose date window (and, if set, nightly
    hour window) covers `now`, the lowest priority number wins; ties fall back
    to the cheapest price. An empty date_start / date_end means "open ended"
    on that side; empty daily_start_hour / daily_end_hour means "active all day".
    A special with a quantity quota that has sold out is excluded even if its
    date window is still open — the deal ends early, the product does not."""
    moment = to_naive_utc(now) or datetime.utcnow()
    live = []
    for s in specials:
        if s.quantity is not None and (s.quantity_sold or 0) >= s.quantity:
            continue
        start = to_naive_utc(s.date_start)
        end = to_naive_utc(s.date_end)
        if (start is None or start <= moment) and (end is None or end >= moment):
            if in_daily_window(moment, s.daily_start_hour, s.daily_end_hour):
                live.append(s)
    if not live:
        return None
    return sorted(live, key=lambda s: (s.priority, s.price))[0]
