from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

OffersTabPanel = Literal["grid", "bundles", "coupons"]


class DealsTab(BaseModel):
    id: str
    label: str
    icon: str = ""
    iconActive: str = ""
    hidden: bool = False
    showAll: bool = False
    panel: OffersTabPanel = "grid"
    categorySlugs: List[str] = Field(default_factory=list)
    productSlugs: List[str] = Field(default_factory=list)


class DealsPageContent(BaseModel):
    title: str = "Excellent Tech Deals"
    subtitle: str = ""
    tabs: List[DealsTab] = Field(default_factory=list)


class WebsiteDealsPageRead(BaseModel):
    id: str
    company_id: str
    content: DealsPageContent
    created_at: datetime
    updated_at: datetime


class WebsiteDealsPageResponse(BaseModel):
    data: WebsiteDealsPageRead


class WebsiteDealsPageUpdate(BaseModel):
    content: DealsPageContent


class StorefrontDealsPageResponse(BaseModel):
    data: DealsPageContent
