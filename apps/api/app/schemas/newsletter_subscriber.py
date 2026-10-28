from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class NewsletterSubscribeRequest(BaseModel):
    """One field on the storefront footer: an email or a BD mobile number."""

    contact: str = Field(..., min_length=3, max_length=255)


class NewsletterSubscribeResponse(BaseModel):
    data: dict


class NewsletterSubscriberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    phone: str
    source: str
    is_active: bool
    created_at: datetime


class NewsletterSubscriberListMeta(BaseModel):
    count: int
    active_count: int


class NewsletterSubscriberListResponse(BaseModel):
    data: List[NewsletterSubscriberRead]
    meta: NewsletterSubscriberListMeta
