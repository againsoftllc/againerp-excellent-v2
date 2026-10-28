"""Storefront PC Builder saved builds — share by code, list per signed-in customer.

The builder's slots come from the Again Builder tool config (not a configurator
profile), so a build is stored as plain slot → product-slug pairs and the
storefront resolves the products from the live catalog when it loads one.
"""

from __future__ import annotations

import json
import secrets
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.storefront_customer_auth import (
    CustomerAuthContext,
    get_current_storefront_customer,
    get_optional_storefront_customer,
)
from app.models.storefront_pc_build import StorefrontPcBuild
from app.services.ecommerce.storefront_feature_flags import require_storefront_flag

router = APIRouter(prefix="/pc-builds", tags=["storefront-pc-builds"])

MAX_BUILDS_PER_CUSTOMER = 50


class PcBuildItem(BaseModel):
    slot: str = Field(min_length=1, max_length=64)
    slug: str = Field(min_length=1, max_length=255)


class PcBuildCreate(BaseModel):
    name: str = Field(default="My PC Build", min_length=1, max_length=255)
    items: List[PcBuildItem] = Field(min_length=1, max_length=40)
    total_price: Decimal = Field(default=Decimal("0"), ge=0)


class PcBuildRead(BaseModel):
    build_code: str
    name: str
    items: List[PcBuildItem]
    total_price: Decimal
    created_at: str
    saved: bool


class PcBuildResponse(BaseModel):
    data: PcBuildRead


class PcBuildListResponse(BaseModel):
    data: List[PcBuildRead]


def _items(row: StorefrontPcBuild) -> List[PcBuildItem]:
    try:
        raw = json.loads(row.items_json or "[]")
    except ValueError:
        return []
    return [PcBuildItem(**i) for i in raw if isinstance(i, dict) and i.get("slot") and i.get("slug")]


def _read(row: StorefrontPcBuild) -> PcBuildRead:
    return PcBuildRead(
        build_code=row.build_code,
        name=row.name,
        items=_items(row),
        total_price=row.total_price or Decimal("0"),
        created_at=row.created_at.date().isoformat() if row.created_at else "",
        saved=bool(row.customer_id),
    )


def _new_code(db: Session) -> str:
    for _ in range(10):
        code = f"PC-{secrets.token_hex(4).upper()}"
        if not db.query(StorefrontPcBuild).filter(StorefrontPcBuild.build_code == code).first():
            return code
    raise HTTPException(status_code=500, detail="Could not allocate a build code")


@router.post("", response_model=PcBuildResponse)
def create_pc_build(
    payload: PcBuildCreate,
    db: Session = Depends(get_db),
    ctx: Optional[CustomerAuthContext] = Depends(get_optional_storefront_customer),
) -> PcBuildResponse:
    """Guests get a shareable code; a signed-in customer's build is also kept on their account."""
    require_storefront_flag("pc_builder")
    customer_id = ctx[2].id if ctx else None
    if customer_id:
        count = db.query(StorefrontPcBuild).filter(StorefrontPcBuild.customer_id == customer_id).count()
        if count >= MAX_BUILDS_PER_CUSTOMER:
            raise HTTPException(status_code=400, detail="You have reached the saved builds limit — delete one first")
    row = StorefrontPcBuild(
        build_code=_new_code(db),
        customer_id=customer_id,
        name=payload.name.strip() or "My PC Build",
        items_json=json.dumps([i.model_dump() for i in payload.items]),
        total_price=payload.total_price,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return PcBuildResponse(data=_read(row))


@router.get("", response_model=PcBuildListResponse)
def list_my_pc_builds(
    db: Session = Depends(get_db),
    ctx: CustomerAuthContext = Depends(get_current_storefront_customer),
) -> PcBuildListResponse:
    rows = (
        db.query(StorefrontPcBuild)
        .filter(StorefrontPcBuild.customer_id == ctx[2].id)
        .order_by(StorefrontPcBuild.created_at.desc())
        .all()
    )
    return PcBuildListResponse(data=[_read(r) for r in rows])


@router.get("/{build_code}", response_model=PcBuildResponse)
def get_pc_build(build_code: str, db: Session = Depends(get_db)) -> PcBuildResponse:
    row = db.query(StorefrontPcBuild).filter(StorefrontPcBuild.build_code == build_code.strip().upper()).first()
    if not row:
        raise HTTPException(status_code=404, detail="Build not found")
    return PcBuildResponse(data=_read(row))


@router.delete("/{build_code}", status_code=204)
def delete_my_pc_build(
    build_code: str,
    db: Session = Depends(get_db),
    ctx: CustomerAuthContext = Depends(get_current_storefront_customer),
) -> None:
    row = (
        db.query(StorefrontPcBuild)
        .filter(
            StorefrontPcBuild.build_code == build_code.strip().upper(),
            StorefrontPcBuild.customer_id == ctx[2].id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Build not found")
    db.delete(row)
    db.commit()
