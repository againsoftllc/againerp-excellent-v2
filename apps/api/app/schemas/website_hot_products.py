from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel, Field

from app.schemas.storefront import StorefrontProductRead


class HotProductsTab(BaseModel):
    id: str
    label: str
    hidden: bool = False
    showAll: bool = False
    categorySlugs: List[str] = Field(default_factory=list)
    productSlugs: List[str] = Field(default_factory=list)


class HotProductsContent(BaseModel):
    title: str = "Hot Products"
    subtitle: str = ""
    bannerUrl: str = ""
    tabs: List[HotProductsTab] = Field(default_factory=list)
    productSlugs: List[str] = Field(default_factory=list)


class WebsiteHotProductsRead(BaseModel):
    id: str
    company_id: str
    content: HotProductsContent
    created_at: datetime
    updated_at: datetime


class WebsiteHotProductsResponse(BaseModel):
    data: WebsiteHotProductsRead


class WebsiteHotProductsUpdate(BaseModel):
    content: HotProductsContent


class StorefrontHotProductsData(HotProductsContent):
    curated: bool = False
    products: List[StorefrontProductRead] = Field(default_factory=list)
    productTabIds: Dict[str, List[str]] = Field(default_factory=dict)


class StorefrontHotProductsResponse(BaseModel):
    data: StorefrontHotProductsData
