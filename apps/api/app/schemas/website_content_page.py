"""Per-page content shapes for about-us, contact-us and outlets.

Each page gets its own model rather than a free-form blob, so the editor cannot
save something the storefront has no way to render — the mistake surfaces on
save instead of as a broken public page.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field


# ── about-us ──────────────────────────────────────────────────────────────────

class KeyFact(BaseModel):
    label: str = ""
    value: str = ""


class IconItem(BaseModel):
    """A labelled item with a Material/asset icon name."""

    icon: str = ""
    label: str = ""


class MissionItem(BaseModel):
    """One spoke of the mission dial. Its angle is layout, so it is not stored."""

    bold: str = ""
    rest: str = ""
    line2: str = ""


class Leader(BaseModel):
    photo: str = ""
    alt: str = ""
    name: str = ""
    role: str = ""
    paragraphs: List[str] = Field(default_factory=list)


class AboutContent(BaseModel):
    intro: str = ""
    # The brand-partner strip is a real content image — the line-up changes — so
    # it is pickable from the gallery. Blank means "use the bundled artwork".
    brands_image: str = Field(default="", alias="brandsImage")
    brands_alt: str = Field(default="", alias="brandsAlt")
    key_facts: List[KeyFact] = Field(default_factory=list, alias="keyFacts")
    brand_assurances: List[IconItem] = Field(default_factory=list, alias="brandAssurances")
    business_intro: str = Field(default="", alias="businessIntro")
    business_items: List[IconItem] = Field(default_factory=list, alias="businessItems")
    mission_items: List[MissionItem] = Field(default_factory=list, alias="missionItems")
    vision: List[str] = Field(default_factory=list)
    leaders: List[Leader] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── contact-us ────────────────────────────────────────────────────────────────

class Branch(BaseModel):
    icon: str = ""
    name: str = ""
    address: List[str] = Field(default_factory=list)
    phone: str = ""
    map: str = ""


class ContactContent(BaseModel):
    map_embed: str = Field(default="", alias="mapEmbed")
    branches: List[Branch] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── outlets ───────────────────────────────────────────────────────────────────

class Outlet(BaseModel):
    photo: str = ""
    alt: str = ""
    icon: str = ""
    filled: bool = False
    name: str = ""
    address: List[str] = Field(default_factory=list)
    phone: str = ""
    hours: str = ""
    note: str = ""
    map: str = ""


class OutletsContent(BaseModel):
    outlets: List[Outlet] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── wiring ────────────────────────────────────────────────────────────────────

CONTENT_SCHEMAS: Dict[str, Type[BaseModel]] = {
    "about-us": AboutContent,
    "contact-us": ContactContent,
    "outlets": OutletsContent,
}


class ContentPageRead(BaseModel):
    slug: str
    content: Dict[str, Any]
    updated_at: Optional[datetime] = None


class ContentPageUpdate(BaseModel):
    content: Dict[str, Any]


class ContentPageResponse(BaseModel):
    data: ContentPageRead


class ContentPageListResponse(BaseModel):
    data: List[ContentPageRead]
