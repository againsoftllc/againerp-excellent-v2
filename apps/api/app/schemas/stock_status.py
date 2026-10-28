from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def slugify_code(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return (out or "status")[:40]


class StockStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    label: str
    sort_order: int = 0
    is_active: bool = True
    is_system: bool = False
    counts_as_in_stock: bool = True
    sellable: bool = True
    tracks_quantity: bool = False
    needs_end_date: bool = False
    badge_label: Optional[str] = None
    badge_color: Optional[str] = None
    show_in_filter: bool = True
    contact_phone: Optional[str] = None


class StockStatusCreate(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    code: Optional[str] = Field(default=None, max_length=40)
    sort_order: int = 0
    is_active: bool = True
    counts_as_in_stock: bool = True
    sellable: bool = True
    tracks_quantity: bool = False
    needs_end_date: bool = False
    badge_label: Optional[str] = Field(default=None, max_length=80)
    badge_color: Optional[str] = Field(default=None, max_length=20)
    show_in_filter: bool = True
    contact_phone: Optional[str] = Field(default=None, max_length=30)

    @field_validator("code")
    @classmethod
    def _check_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = slugify_code(v)
        if not CODE_RE.match(v):
            raise ValueError("Code must start with a letter and use lowercase letters, digits or _")
        return v


class StockStatusUpdate(BaseModel):
    """`code` is intentionally absent — products store it as a plain string, so
    renaming it would orphan every product already using this status."""

    label: Optional[str] = Field(default=None, min_length=1, max_length=80)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    counts_as_in_stock: Optional[bool] = None
    sellable: Optional[bool] = None
    tracks_quantity: Optional[bool] = None
    needs_end_date: Optional[bool] = None
    badge_label: Optional[str] = Field(default=None, max_length=80)
    badge_color: Optional[str] = Field(default=None, max_length=20)
    show_in_filter: Optional[bool] = None
    contact_phone: Optional[str] = Field(default=None, max_length=30)


class StockStatusListResponse(BaseModel):
    data: List[StockStatusRead]
    errors: List[str] = []


class StockStatusResponse(BaseModel):
    data: StockStatusRead
    errors: List[str] = []
