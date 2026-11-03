from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


OfferStatus = Literal["draft", "scheduled", "running", "ended", "disabled"]


class OfferDealInput(BaseModel):
    product_slug: str = Field(..., min_length=1, max_length=200)
    offer_price: float = Field(..., gt=0)
    note: Optional[str] = Field(default=None, max_length=255)
    priority: int = 0
    # Deal quota — null means unlimited.
    quantity: Optional[int] = None
    enabled: bool = True
    sort_order: int = 0


class OfferDealRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_slug: str
    offer_price: float
    note: Optional[str] = None
    priority: int
    quantity: Optional[int] = None
    # How many units have sold at this deal's price — read from the synced
    # catalog_product_specials row (checkout increments it there), not stored
    # on the deal itself.
    quantity_sold: int = 0
    enabled: bool = True
    sort_order: int


class OfferSectionInput(BaseModel):
    key: Optional[str] = Field(default=None, max_length=120)
    label: str = Field(..., min_length=1, max_length=160)
    sort_order: int = 0
    deals: List[OfferDealInput] = []


class OfferSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    label: str
    sort_order: int
    deals: List[OfferDealRead] = []


class OfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    slug: str
    title: str
    subtitle: Optional[str] = None
    description: str
    image_url: Optional[str] = None
    # When set, the Offers list card's "View Details" and this offer's own
    # detail URL both redirect here instead of showing its product grid.
    custom_link: Optional[str] = None
    outlet_label: str
    starts_at: datetime
    ends_at: datetime
    # Optional nightly window — both null means "active all day" within the
    # date range above.
    daily_start_hour: Optional[int] = None
    daily_end_hour: Optional[int] = None
    status: str
    terms: List[str] = []
    sort_order: int
    sections: List[OfferSectionRead] = []
    created_at: datetime
    updated_at: datetime


class OfferListMeta(BaseModel):
    count: int


class OfferListResponse(BaseModel):
    data: List[OfferRead]
    meta: OfferListMeta


class OfferResponse(BaseModel):
    data: OfferRead


class OfferCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=160)
    title: str = Field(..., min_length=1, max_length=255)
    subtitle: Optional[str] = Field(default=None, max_length=255)
    description: str = ""
    image_url: Optional[str] = Field(default=None, max_length=500)
    custom_link: Optional[str] = Field(default=None, max_length=500)
    outlet_label: str = Field(default="All Outlet", max_length=120)
    starts_at: datetime
    ends_at: datetime
    daily_start_hour: Optional[int] = Field(default=None, ge=0, le=24)
    daily_end_hour: Optional[int] = Field(default=None, ge=0, le=24)
    status: OfferStatus = "draft"
    terms: List[str] = []
    sort_order: int = 0
    sections: List[OfferSectionInput] = []


class OfferUpdate(BaseModel):
    slug: Optional[str] = Field(default=None, min_length=1, max_length=160)
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    subtitle: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    image_url: Optional[str] = Field(default=None, max_length=500)
    custom_link: Optional[str] = Field(default=None, max_length=500)
    outlet_label: Optional[str] = Field(default=None, max_length=120)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    daily_start_hour: Optional[int] = Field(default=None, ge=0, le=24)
    daily_end_hour: Optional[int] = Field(default=None, ge=0, le=24)
    status: Optional[OfferStatus] = None
    terms: Optional[List[str]] = None
    sort_order: Optional[int] = None
    sections: Optional[List[OfferSectionInput]] = None
