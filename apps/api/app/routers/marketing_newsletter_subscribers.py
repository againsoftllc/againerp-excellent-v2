from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import require_write_access
from app.models.newsletter_subscriber import NewsletterSubscriber
from app.schemas.newsletter_subscriber import (
    NewsletterSubscriberListMeta,
    NewsletterSubscriberListResponse,
    NewsletterSubscriberRead,
)

router = APIRouter(prefix="/marketing/newsletter-subscribers", tags=["marketing-newsletter-subscribers"])


@router.get("", response_model=NewsletterSubscriberListResponse)
def list_newsletter_subscribers(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(default=None),
    active: Optional[bool] = Query(default=None),
) -> NewsletterSubscriberListResponse:
    query = db.query(NewsletterSubscriber).order_by(NewsletterSubscriber.created_at.desc())

    if active is not None:
        query = query.filter(NewsletterSubscriber.is_active == active)
    if search:
        term = f"%{search.strip().lower()}%"
        query = query.filter(
            (NewsletterSubscriber.email.ilike(term)) | (NewsletterSubscriber.phone.ilike(term)),
        )

    rows = query.all()
    data = [NewsletterSubscriberRead.model_validate(row) for row in rows]
    active_count = sum(1 for row in rows if row.is_active)
    return NewsletterSubscriberListResponse(
        data=data,
        meta=NewsletterSubscriberListMeta(count=len(data), active_count=active_count),
    )


@router.delete("/{subscriber_id}", status_code=204)
def delete_newsletter_subscriber(
    subscriber_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> None:
    row = db.get(NewsletterSubscriber, subscriber_id)
    if not row:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    db.delete(row)
    db.commit()
