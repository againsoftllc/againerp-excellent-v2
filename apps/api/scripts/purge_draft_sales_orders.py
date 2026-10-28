"""Soft-delete all draft sales orders (demo / abandoned drafts on the dashboard)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models.sales import SalesOrder
from app.services.sales.sales_service import SalesService


def main() -> None:
    db = SessionLocal()
    try:
        drafts = (
            db.query(SalesOrder)
            .filter(
                SalesOrder.deleted_at.is_(None),
                SalesOrder.status == "draft",
            )
            .order_by(SalesOrder.order_number)
            .all()
        )
        if not drafts:
            print("No draft sales orders found.")
            return

        svc = SalesService(db)
        print(f"Removing {len(drafts)} draft sales order(s):")
        for order in drafts:
            note = (order.notes or "").split("\n", 1)[0][:60]
            print(f"  - {order.order_number}  customer={order.customer_id}  {note!r}")
            svc.delete_order(order.id, actor_id=None)

        db.commit()
        remaining = (
            db.query(SalesOrder)
            .filter(SalesOrder.deleted_at.is_(None), SalesOrder.status == "draft")
            .count()
        )
        print(f"Done. Active draft sales orders remaining: {remaining}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
