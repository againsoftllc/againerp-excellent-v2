"""The storefront's contact form inbox (Branches page -> "Send Us a Message"): what visitors wrote, for Admin -> Website -> Site -> Messages.

The public form saves a row in `website_contact_submissions` (status "new"); this router lets the admin read them, mark them and delete them."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_company_id, require_write_access
from app.models.website_contact_submission import WebsiteContactSubmission

router = APIRouter(prefix="/website/contact-messages", tags=["website-contact-messages"])

STATUSES = ("new", "read", "done")


class ContactMessageRead(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    subject: str
    message: str
    status: str
    created_at: datetime


class ContactMessageListMeta(BaseModel):
    count: int
    new: int


class ContactMessageListResponse(BaseModel):
    data: List[ContactMessageRead]
    meta: ContactMessageListMeta


class ContactMessageStatusWrite(BaseModel):
    status: str = Field(pattern="^(new|read|done)$")


class ContactMessageResponse(BaseModel):
    data: ContactMessageRead


def _read(row: WebsiteContactSubmission) -> ContactMessageRead:
    return ContactMessageRead(
        id=row.id,
        name=row.name or "",
        email=row.email or "",
        phone=row.phone or "",
        subject=row.subject or "",
        message=row.message or "",
        status=row.status if row.status in STATUSES else "new",
        created_at=row.created_at,
    )


def _mine(db: Session, company_id: str):
    # the public form saves under the default company
    return db.query(WebsiteContactSubmission).filter(func.coalesce(WebsiteContactSubmission.company_id, "default") == company_id)


@router.get("", response_model=ContactMessageListResponse)
def list_contact_messages(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
) -> ContactMessageListResponse:
    query = _mine(db, company_id)
    new_count = query.filter(WebsiteContactSubmission.status == "new").count()
    if status in STATUSES:
        query = query.filter(WebsiteContactSubmission.status == status)
    rows = query.order_by(WebsiteContactSubmission.created_at.desc()).limit(limit).all()
    data = [_read(r) for r in rows]
    return ContactMessageListResponse(data=data, meta=ContactMessageListMeta(count=len(data), new=new_count))


@router.patch("/{message_id}", response_model=ContactMessageResponse)
def set_contact_message_status(
    message_id: str,
    payload: ContactMessageStatusWrite,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    _: object = Depends(require_write_access),
) -> ContactMessageResponse:
    row = _mine(db, company_id).filter(WebsiteContactSubmission.id == message_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    row.status = payload.status
    db.commit()
    db.refresh(row)
    return ContactMessageResponse(data=_read(row))


@router.delete("/{message_id}", status_code=204)
def delete_contact_message(
    message_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    _: object = Depends(require_write_access),
) -> None:
    row = _mine(db, company_id).filter(WebsiteContactSubmission.id == message_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    db.delete(row)
    db.commit()
