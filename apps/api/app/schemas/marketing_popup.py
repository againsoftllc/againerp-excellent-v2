from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["happy_hour", "offer", "notice", "image"]
Status = Literal["draft", "active", "disabled"]
Frequency = Literal["session", "days", "always"]
Pages = Literal["home", "all", "paths"]
Devices = Literal["all", "desktop", "mobile"]


class PopupWrite(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kind: Kind = "notice"
    status: Status = "draft"
    title: str = Field(default="", max_length=255)
    body: str = ""
    image_url: Optional[str] = Field(default=None, max_length=500)
    button_label: str = Field(default="", max_length=80)
    link_url: str = Field(default="", max_length=500)
    campaign_slug: str = Field(default="", max_length=160)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    delay_seconds: int = Field(default=5, ge=0, le=600)
    frequency: Frequency = "session"
    frequency_days: int = Field(default=1, ge=1, le=365)
    pages: Pages = "home"
    paths: List[str] = Field(default_factory=list)
    devices: Devices = "all"
    priority: int = 0


class PopupUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    kind: Optional[Kind] = None
    status: Optional[Status] = None
    title: Optional[str] = Field(default=None, max_length=255)
    body: Optional[str] = None
    image_url: Optional[str] = Field(default=None, max_length=500)
    button_label: Optional[str] = Field(default=None, max_length=80)
    link_url: Optional[str] = Field(default=None, max_length=500)
    campaign_slug: Optional[str] = Field(default=None, max_length=160)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    delay_seconds: Optional[int] = Field(default=None, ge=0, le=600)
    frequency: Optional[Frequency] = None
    frequency_days: Optional[int] = Field(default=None, ge=1, le=365)
    pages: Optional[Pages] = None
    paths: Optional[List[str]] = None
    devices: Optional[Devices] = None
    priority: Optional[int] = None


class PopupRead(PopupWrite):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class PopupResponse(BaseModel):
    data: PopupRead


class PopupListResponse(BaseModel):
    data: List[PopupRead]
