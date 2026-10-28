from __future__ import annotations

import uuid
from datetime import datetime
from typing import List

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base


class CatalogProductRelated(Base):
    """Manually paired products — what the shop shows as "Frequently Paired".

    Pairs are symmetric: adding B to A's list also puts A in B's, so a merchant
    never has to enter the same pairing twice. Both directions are stored as
    their own row, which keeps reads a single indexed lookup instead of an OR
    across two columns.
    """

    __tablename__ = "catalog_product_related"
    __table_args__ = (
        UniqueConstraint("product_id", "related_id", name="uq_catalog_product_related_pair"),
    )

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
    related_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("catalog_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )


def list_related_ids(db: Session, product_id: str) -> List[str]:
    rows = (
        db.query(CatalogProductRelated)
        .filter(CatalogProductRelated.product_id == product_id)
        .order_by(CatalogProductRelated.sort_order, CatalogProductRelated.created_at)
        .all()
    )
    return [row.related_id for row in rows]


def replace_related(
    db: Session,
    product_id: str,
    related_ids: List[str],
    *,
    company_id: str = "default",
) -> List[str]:
    """Set this product's pairs, keeping every partner's list in sync.

    Dropping B from A's list also drops A from B's — a pairing means the same
    thing seen from either side, so a one-sided removal would leave the shop
    showing a pair only one of the two products still claims.
    """
    wanted: List[str] = []
    for rid in related_ids:
        # Self-pairing would make a product suggest itself.
        if rid and rid != product_id and rid not in wanted:
            wanted.append(rid)

    existing = set(list_related_ids(db, product_id))

    for rid in existing - set(wanted):
        db.query(CatalogProductRelated).filter(
            CatalogProductRelated.product_id.in_([product_id, rid]),
            CatalogProductRelated.related_id.in_([product_id, rid]),
        ).delete(synchronize_session=False)

    for idx, rid in enumerate(wanted):
        forward = (
            db.query(CatalogProductRelated)
            .filter(
                CatalogProductRelated.product_id == product_id,
                CatalogProductRelated.related_id == rid,
            )
            .first()
        )
        if forward:
            forward.sort_order = idx
        else:
            db.add(
                CatalogProductRelated(
                    company_id=company_id,
                    product_id=product_id,
                    related_id=rid,
                    sort_order=idx,
                )
            )

        mirror_exists = (
            db.query(CatalogProductRelated)
            .filter(
                CatalogProductRelated.product_id == rid,
                CatalogProductRelated.related_id == product_id,
            )
            .first()
        )
        if not mirror_exists:
            # Appended at the end of the partner's own order — its existing
            # arrangement is the merchant's, not ours to reshuffle.
            tail = (
                db.query(func.coalesce(func.max(CatalogProductRelated.sort_order), -1))
                .filter(CatalogProductRelated.product_id == rid)
                .scalar()
            )
            db.add(
                CatalogProductRelated(
                    company_id=company_id,
                    product_id=rid,
                    related_id=product_id,
                    sort_order=int(tail) + 1,
                )
            )

    db.flush()
    return wanted
