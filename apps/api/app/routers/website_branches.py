from __future__ import annotations

import json
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import require_write_access
from app.models.platform_setting import PlatformSetting
from app.services.ecommerce.checkout_shipping_availability import (
    load_shipping_settings,
    parse_pickup_points,
)

router = APIRouter(prefix="/website/branches", tags=["website-branches"])

SETTING_KEY = "shipping.pickup_points"


class BranchItem(BaseModel):
    """One branch = one store-pickup counter (the same list checkout offers for Store Pickup)."""

    key: str = Field(default="", max_length=80)
    label: str = Field(min_length=1, max_length=120)
    address: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=120)
    map_url: str = Field(default="", max_length=1000)
    image: str = Field(default="", max_length=500)
    hours: str = Field(default="", max_length=300)
    whatsapp: str = Field(default="", max_length=60)
    email: str = Field(default="", max_length=160)
    visible: bool = True


class BranchListWrite(BaseModel):
    branches: List[BranchItem]


class BranchListResponse(BaseModel):
    data: List[BranchItem]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "branch"


def _read(db: Session) -> List[BranchItem]:
    raw = load_shipping_settings(db).get(SETTING_KEY)
    return [
        BranchItem(
            key=p["key"], label=p["label"], address=p["address"], phone=p["phone"], map_url=p["map_url"],
            image=p.get("image", ""), hours=p.get("hours", ""), whatsapp=p.get("whatsapp", ""), email=p.get("email", ""),
            visible=p.get("visible", "true") != "false",
        )
        for p in parse_pickup_points(raw)
    ]


@router.get("", response_model=BranchListResponse)
def list_branches(db: Session = Depends(get_db)) -> BranchListResponse:
    return BranchListResponse(data=_read(db))


@router.put("", response_model=BranchListResponse)
def replace_branches(
    payload: BranchListWrite, db: Session = Depends(get_db), _: object = Depends(require_write_access)
) -> BranchListResponse:
    """Replace the whole list (the admin reorders / edits / removes in one go). The key is what an order remembers, so a
    branch that keeps its key keeps its history; a new branch gets a key from its name."""
    if not payload.branches:
        raise HTTPException(status_code=400, detail="Keep at least one branch - customers who pick Store Pickup must be told where to go")
    seen: set[str] = set()
    out: List[dict] = []
    for item in payload.branches:
        key = item.key.strip() or _slug(item.label)
        base, n = key, 2
        while key in seen:
            key, n = f"{base}-{n}", n + 1
        seen.add(key)
        out.append(
            {
                "key": key, "label": item.label.strip(), "address": item.address.strip(), "phone": item.phone.strip(),
                "map_url": item.map_url.strip(), "image": item.image.strip(), "hours": item.hours.strip(),
                "whatsapp": item.whatsapp.strip(), "email": item.email.strip(), "visible": "true" if item.visible else "false",
            }
        )
    value = json.dumps(out, ensure_ascii=False)
    row = db.query(PlatformSetting).filter(PlatformSetting.key == SETTING_KEY).first()
    if row:
        row.value = value
    else:
        db.add(PlatformSetting(key=SETTING_KEY, value=value, description="Store pickup branches", is_secret=False))
    db.commit()
    return BranchListResponse(data=_read(db))
