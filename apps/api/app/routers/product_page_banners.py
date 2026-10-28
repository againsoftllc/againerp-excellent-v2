from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import require_write_access
from app.models.product_page_banner import ProductPageBanner
from app.schemas.product_page_banner import (
    ProductPageBannerCreate,
    ProductPageBannerListResponse,
    ProductPageBannerRead,
    ProductPageBannerResponse,
    ProductPageBannerUpdate,
)

router = APIRouter(prefix="/product-page-banners", tags=["product-page-banners"])


def _to_read(row: ProductPageBanner) -> ProductPageBannerRead:
    data = ProductPageBannerRead.model_validate(row).model_dump()
    data["target_category_ids"] = json.loads(row.target_category_ids_json or "[]")
    data["target_product_ids"] = json.loads(row.target_product_ids_json or "[]")
    return ProductPageBannerRead(**data)


def _apply(row: ProductPageBanner, payload: dict) -> None:
    if "target_category_ids" in payload:
        row.target_category_ids_json = json.dumps(payload.pop("target_category_ids") or [])
    if "target_product_ids" in payload:
        row.target_product_ids_json = json.dumps(payload.pop("target_product_ids") or [])
    for key, value in payload.items():
        setattr(row, key, value)


@router.get("", response_model=ProductPageBannerListResponse)
def list_banners(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(default=None),
) -> ProductPageBannerListResponse:
    query = db.query(ProductPageBanner).order_by(
        ProductPageBanner.sort_order.asc(), ProductPageBanner.created_at.desc()
    )
    if search:
        term = f"%{search.strip().lower()}%"
        query = query.filter(ProductPageBanner.name.ilike(term))
    rows = query.all()
    return ProductPageBannerListResponse(
        data=[_to_read(row) for row in rows],
        meta={"count": len(rows)},
    )


@router.post("", response_model=ProductPageBannerResponse, status_code=201)
def create_banner(
    payload: ProductPageBannerCreate,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> ProductPageBannerResponse:
    data = payload.model_dump()
    row = ProductPageBanner(
        name=data.pop("name"),
        image_url=data.pop("image_url"),
        link_href=data.pop("link_href"),
        alt_text=data.pop("alt_text"),
        target_type=data.pop("target_type"),
        is_active=data.pop("is_active"),
        sort_order=data.pop("sort_order"),
        target_category_ids_json=json.dumps(data.pop("target_category_ids") or []),
        target_product_ids_json=json.dumps(data.pop("target_product_ids") or []),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ProductPageBannerResponse(data=_to_read(row))


@router.patch("/{banner_id}", response_model=ProductPageBannerResponse)
def update_banner(
    banner_id: str,
    payload: ProductPageBannerUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> ProductPageBannerResponse:
    row = db.get(ProductPageBanner, banner_id)
    if not row:
        raise HTTPException(status_code=404, detail="Banner not found")
    _apply(row, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(row)
    return ProductPageBannerResponse(data=_to_read(row))


@router.delete("/{banner_id}", status_code=204)
def delete_banner(
    banner_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> None:
    row = db.get(ProductPageBanner, banner_id)
    if not row:
        raise HTTPException(status_code=404, detail="Banner not found")
    db.delete(row)
    db.commit()
