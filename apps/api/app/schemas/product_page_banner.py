from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

BannerTargetType = Literal["all", "category", "product"]


class ProductPageBannerBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    image_url: str = Field(default="", max_length=500)
    link_href: str = Field(default="", max_length=500)
    alt_text: str = Field(default="", max_length=255)
    target_type: BannerTargetType = "all"
    target_category_ids: List[str] = Field(default_factory=list)
    target_product_ids: List[str] = Field(default_factory=list)
    is_active: bool = True
    sort_order: int = 0


class ProductPageBannerCreate(ProductPageBannerBase):
    pass


class ProductPageBannerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    image_url: Optional[str] = Field(default=None, max_length=500)
    link_href: Optional[str] = Field(default=None, max_length=500)
    alt_text: Optional[str] = Field(default=None, max_length=255)
    target_type: Optional[BannerTargetType] = None
    target_category_ids: Optional[List[str]] = None
    target_product_ids: Optional[List[str]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ProductPageBannerRead(ProductPageBannerBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class ProductPageBannerListResponse(BaseModel):
    data: List[ProductPageBannerRead]
    meta: dict


class ProductPageBannerResponse(BaseModel):
    data: ProductPageBannerRead


class StorefrontPageBanner(BaseModel):
    """What the storefront actually needs to render a matched banner."""

    id: str
    image_url: str
    link_href: str
    alt_text: str
