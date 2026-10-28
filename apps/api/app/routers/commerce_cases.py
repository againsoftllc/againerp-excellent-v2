"""Cross-customer QC / Complaint / Support queues.

`commerce_customers.py` already has full case CRUD scoped to one customer
(`/customers/{customer_id}/cases/...`) — this router only adds the read-side
"every case of this type, across every customer" view a dedicated team needs
to work a queue instead of hunting through customer profiles one by one.
Replying/closing still goes through the existing customer-scoped endpoints,
since each row here already carries the `customer_id` needed to call them.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import require_permission
from app.models.auth_user import AuthUser
from app.models.commerce_customer import CommerceCustomer, load_json
from app.models.storefront_customer_auth import StorefrontCustomerCase
from app.schemas.commerce_customer import CustomerCaseReplyRead

router = APIRouter(prefix="/cases", tags=["commerce-cases"])


class GlobalCaseRead(BaseModel):
    id: str
    case_number: str
    case_type: str
    date: str
    customer_id: str
    customer_name: str
    order_id: Optional[str] = None
    order_number: Optional[str] = None
    subject: str
    message: str
    product_label: Optional[str] = None
    status: str
    manager_name: Optional[str] = None
    replies: List[CustomerCaseReplyRead]


class GlobalCaseListResponse(BaseModel):
    data: List[GlobalCaseRead]


def _replies(row: StorefrontCustomerCase) -> List[CustomerCaseReplyRead]:
    raw = load_json(getattr(row, "replies_json", None), [])
    if not isinstance(raw, list):
        return []
    out: List[CustomerCaseReplyRead] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or "").strip()
        if not message:
            continue
        out.append(
            CustomerCaseReplyRead(
                id=str(item.get("id") or ""),
                at=str(item.get("at") or ""),
                author=str(item.get("author") or "Admin"),
                role=str(item.get("role") or "admin"),
                message=message,
            )
        )
    return out


@router.get("", response_model=GlobalCaseListResponse)
def list_cases(
    case_type: str = Query(..., pattern="^(support|complaint|qc)$"),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _: AuthUser = Depends(require_permission("customers", "read")),
) -> GlobalCaseListResponse:
    q = (
        db.query(StorefrontCustomerCase, CommerceCustomer)
        .join(CommerceCustomer, CommerceCustomer.id == StorefrontCustomerCase.customer_id)
        .filter(StorefrontCustomerCase.case_type == case_type)
    )
    if status:
        q = q.filter(StorefrontCustomerCase.status == status)
    rows = q.order_by(StorefrontCustomerCase.created_at.desc()).all()
    return GlobalCaseListResponse(
        data=[
            GlobalCaseRead(
                id=case.id,
                case_number=case.case_number,
                case_type=case.case_type,
                date=case.created_at.strftime("%Y-%m-%d") if case.created_at else "",
                customer_id=customer.id,
                customer_name=customer.name or customer.email or "Customer",
                order_id=case.order_id,
                order_number=case.order_number,
                subject=case.subject or "",
                message=case.message or "",
                product_label=case.product_label,
                status=case.status or "open",
                manager_name=case.manager_name,
                replies=_replies(case),
            )
            for case, customer in rows
        ]
    )
