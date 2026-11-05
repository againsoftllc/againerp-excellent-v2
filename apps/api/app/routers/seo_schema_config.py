"""Schema (JSON-LD) and meta-title settings of the storefront: edited in Admin -> SEO -> Config -> Schema & meta templates,
read by the storefront for every page. One JSON document in `platform_settings`; anything missing falls back to the defaults,
and the storefront falls back to the shop's own settings (name, logo, phones ...) for blank business fields."""
from __future__ import annotations

import json
from typing import List, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import require_write_access
from app.models.platform_setting import PlatformSetting

SETTING_KEY = "seo.schema_config"

router = APIRouter(prefix="/seo/schema-config", tags=["seo-schema-config"])
public_router = APIRouter(tags=["storefront-seo-config"])


class Address(BaseModel):
    street: str = Field(default="", max_length=300)
    locality: str = Field(default="Dhaka", max_length=120)
    region: str = Field(default="", max_length=120)
    postal_code: str = Field(default="", max_length=30)
    country: str = Field(default="BD", max_length=2)


class Social(BaseModel):
    facebook: str = Field(default="", max_length=300)
    instagram: str = Field(default="", max_length=300)
    youtube: str = Field(default="", max_length=300)
    tiktok: str = Field(default="", max_length=300)
    x: str = Field(default="", max_length=300)
    linkedin: str = Field(default="", max_length=300)


class Business(BaseModel):
    name: str = Field(default="", max_length=160)
    legal_name: str = Field(default="", max_length=200)
    logo_url: str = Field(default="", max_length=500)
    phones: List[str] = Field(default_factory=list)
    email: str = Field(default="", max_length=160)
    store_type: Literal["OnlineStore", "Store", "ElectronicsStore", "LocalBusiness"] = "OnlineStore"
    price_range: str = Field(default="", max_length=20)
    address: Address = Field(default_factory=Address)
    social: Social = Field(default_factory=Social)


class Pages(BaseModel):
    home: bool = True
    category: bool = True
    brand: bool = True
    product: bool = True
    branches: bool = True
    offers: bool = True
    info: bool = True


class ProductDefaults(BaseModel):
    item_condition: Literal["NewCondition", "UsedCondition", "RefurbishedCondition"] = "NewCondition"
    # days a price stays valid in the Offer (0 = leave it out)
    price_valid_days: int = Field(default=30, ge=0, le=365)
    # return policy: days (0 = leave it out) and the page that explains it
    return_days: int = Field(default=0, ge=0, le=365)
    return_policy_url: str = Field(default="", max_length=300)


class MetaTemplates(BaseModel):
    """Title / description patterns. Tokens: {name} {brand} {category} {site} {sku} {price}. Empty = the page's own wording."""

    home_title: str = Field(default="", max_length=200)
    home_description: str = Field(default="", max_length=400)
    category_title: str = Field(default="", max_length=200)
    category_description: str = Field(default="", max_length=400)
    brand_title: str = Field(default="", max_length=200)
    brand_description: str = Field(default="", max_length=400)
    product_title: str = Field(default="", max_length=200)
    product_description: str = Field(default="", max_length=400)


class SeoSchemaConfig(BaseModel):
    enabled: bool = True
    business: Business = Field(default_factory=Business)
    pages: Pages = Field(default_factory=Pages)
    product: ProductDefaults = Field(default_factory=ProductDefaults)
    meta: MetaTemplates = Field(default_factory=MetaTemplates)


class SeoSchemaConfigResponse(BaseModel):
    data: SeoSchemaConfig


def load_config(db: Session) -> SeoSchemaConfig:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == SETTING_KEY).first()
    if row and (row.value or "").strip():
        try:
            return SeoSchemaConfig.model_validate(json.loads(row.value))
        except (ValueError, TypeError):
            pass  # an unreadable document is the defaults, never an error page
    return SeoSchemaConfig()


@router.get("", response_model=SeoSchemaConfigResponse)
def get_config(db: Session = Depends(get_db)) -> SeoSchemaConfigResponse:
    return SeoSchemaConfigResponse(data=load_config(db))


@router.put("", response_model=SeoSchemaConfigResponse)
def save_config(
    payload: SeoSchemaConfig, db: Session = Depends(get_db), _: object = Depends(require_write_access)
) -> SeoSchemaConfigResponse:
    value = payload.model_dump_json()
    row = db.query(PlatformSetting).filter(PlatformSetting.key == SETTING_KEY).first()
    if row:
        row.value = value
    else:
        db.add(PlatformSetting(key=SETTING_KEY, value=value, description="Storefront schema (JSON-LD) and meta templates", is_secret=False))
    db.commit()
    return SeoSchemaConfigResponse(data=load_config(db))


@public_router.get("/seo-config", response_model=SeoSchemaConfigResponse)
def storefront_seo_config(response: Response, db: Session = Depends(get_db)) -> SeoSchemaConfigResponse:
    """What the storefront needs to build its JSON-LD and meta titles (nothing here is secret)."""
    response.headers["Cache-Control"] = "public, max-age=60"
    return SeoSchemaConfigResponse(data=load_config(db))


# ---- robots.txt -------------------------------------------------------------------------------------------------------
ROBOTS_KEY = "seo.robots"
DEFAULT_ROBOTS_TEXT = "\n".join(
    ["User-agent: *", "Allow: /", "Disallow: /cart", "Disallow: /checkout", "Disallow: /account", "Disallow: /website/", "Disallow: /api/"]
)


class RobotsConfig(BaseModel):
    # Closed by default: a shop that was never configured must not open itself to crawlers by accident.
    block_all: bool = True
    text: str = Field(default=DEFAULT_ROBOTS_TEXT, max_length=5000)


class RobotsConfigResponse(BaseModel):
    data: RobotsConfig


def load_robots(db: Session) -> RobotsConfig:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == ROBOTS_KEY).first()
    if row and (row.value or "").strip():
        try:
            return RobotsConfig.model_validate(json.loads(row.value))
        except (ValueError, TypeError):
            pass  # an unreadable document is the (closed) defaults, never an error page
    return RobotsConfig()


@router.get("/robots", response_model=RobotsConfigResponse)
def get_robots(db: Session = Depends(get_db)) -> RobotsConfigResponse:
    return RobotsConfigResponse(data=load_robots(db))


@router.put("/robots", response_model=RobotsConfigResponse)
def save_robots(
    payload: RobotsConfig, db: Session = Depends(get_db), _: object = Depends(require_write_access)
) -> RobotsConfigResponse:
    value = payload.model_dump_json()
    row = db.query(PlatformSetting).filter(PlatformSetting.key == ROBOTS_KEY).first()
    if row:
        row.value = value
    else:
        db.add(PlatformSetting(key=ROBOTS_KEY, value=value, description="Storefront robots.txt", is_secret=False))
    db.commit()
    return RobotsConfigResponse(data=load_robots(db))


@public_router.get("/robots-config", response_model=RobotsConfigResponse)
def storefront_robots_config(response: Response, db: Session = Depends(get_db)) -> RobotsConfigResponse:
    response.headers["Cache-Control"] = "public, max-age=60"
    return RobotsConfigResponse(data=load_robots(db))
