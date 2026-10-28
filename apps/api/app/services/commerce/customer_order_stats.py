"""One answer to "how many orders has this customer placed, and where are they?"

A storefront purchase is written twice: once as a CommerceOrder and again as a
mirrored SalesOrder carrying the same order number, so counting both tables
double-counts every web order. The two tables also spell their stages
differently — commerce says "packed"/"shipped", sales says "processing" — so
each side used to bucket orders its own way and disagree with the other.

Both panels read their totals from here instead: the same de-duplicated set of
orders, sorted into the same four buckets, so the customer and the staff serving
them never see different numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.commerce_order import CommerceOrder
from app.models.sales import SalesOrder

# Every status either side can store maps to exactly one bucket. A status in no
# bucket would be counted in the total but shown nowhere, which is how cancelled
# orders used to vanish from the customer's dashboard.
_BUCKET_BY_STATUS: dict[str, str] = {
    "draft": "pending",
    "pending": "pending",
    "confirmed": "pending",
    "processing": "processing",
    "packed": "processing",
    "shipped": "processing",
    "delivered": "completed",
    "completed": "completed",
    "cancelled": "cancelled",
    "returned": "cancelled",
    "refunded": "cancelled",
    "failed": "cancelled",
}

BUCKET_LABELS: list[tuple[str, str]] = [
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]


def bucket_for_status(status: Optional[str]) -> str:
    """An unknown status is treated as still in flight rather than dropped."""
    return _BUCKET_BY_STATUS.get((status or "").strip().lower(), "pending")


@dataclass
class CustomerOrderStats:
    total: int = 0
    pending: int = 0
    processing: int = 0
    completed: int = 0
    cancelled: int = 0
    total_spend: Decimal = field(default_factory=lambda: Decimal("0"))

    def count_of(self, bucket: str) -> int:
        return int(getattr(self, bucket, 0))

    def pct_of(self, bucket: str) -> int:
        if self.total <= 0:
            return 0
        return int(round(self.count_of(bucket) * 100 / self.total))

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "pending": self.pending,
            "processing": self.processing,
            "completed": self.completed,
            "cancelled": self.cancelled,
            "total_spend": self.total_spend,
        }


def _normalise_number(order_number: Optional[str]) -> str:
    """Match the two tables' spellings of the same order.

    The mirror truncates to 32 characters and the admin list prefixes a "#",
    so compare on the bare, trimmed number.
    """
    return (order_number or "").strip().lstrip("#")[:32].upper()


def dedupe_orders(
    commerce_orders: Iterable[CommerceOrder],
    sales_orders: Iterable[SalesOrder],
) -> tuple[list[CommerceOrder], list[SalesOrder]]:
    """Drop the mirrored copy, keeping the commerce row the shopper placed.

    Admin-created sales orders have no commerce twin and are kept in full.
    """
    commerce = list(commerce_orders)
    seen = {_normalise_number(o.order_number) for o in commerce}
    seen.discard("")
    admin_only = [o for o in sales_orders if _normalise_number(o.order_number) not in seen]
    return commerce, admin_only


def collect_customer_orders(
    db: Session,
    customer_id: str,
) -> tuple[list[CommerceOrder], list[SalesOrder]]:
    """Every order belonging to this customer, each counted once."""
    commerce_orders = (
        db.query(CommerceOrder)
        .filter(CommerceOrder.customer_id == customer_id)
        .order_by(CommerceOrder.order_date.desc())
        .all()
    )
    sales_orders = (
        db.query(SalesOrder)
        .filter(
            SalesOrder.customer_id == customer_id,
            SalesOrder.deleted_at.is_(None),
        )
        .order_by(SalesOrder.order_date.desc())
        .all()
    )
    return dedupe_orders(commerce_orders, sales_orders)


def stats_from_orders(
    commerce_orders: Iterable[CommerceOrder],
    sales_orders: Iterable[SalesOrder],
) -> CustomerOrderStats:
    stats = CustomerOrderStats()
    for order in commerce_orders:
        stats.total += 1
        bucket = bucket_for_status(order.status)
        setattr(stats, bucket, getattr(stats, bucket) + 1)
        if bucket != "cancelled":
            stats.total_spend += Decimal(str(order.grand_total or 0))
    for order in sales_orders:
        stats.total += 1
        bucket = bucket_for_status(order.status)
        setattr(stats, bucket, getattr(stats, bucket) + 1)
        if bucket != "cancelled":
            stats.total_spend += Decimal(str(order.total or 0))
    return stats


def customer_order_stats(db: Session, customer_id: str) -> CustomerOrderStats:
    commerce_orders, sales_orders = collect_customer_orders(db, customer_id)
    return stats_from_orders(commerce_orders, sales_orders)
