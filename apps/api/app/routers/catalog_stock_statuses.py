from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import require_permission
from app.models.auth_user import AuthUser
from app.models.catalog_product import CatalogProduct
from app.models.catalog_stock_status import (
    CatalogStockStatus,
    ensure_default_stock_statuses,
)
from app.schemas.stock_status import (
    StockStatusCreate,
    StockStatusListResponse,
    StockStatusRead,
    StockStatusResponse,
    StockStatusUpdate,
    slugify_code,
)

router = APIRouter(prefix="/stock-statuses", tags=["catalog-stock-statuses"])


def _ordered(db: Session) -> List[CatalogStockStatus]:
    return (
        db.query(CatalogStockStatus)
        .order_by(CatalogStockStatus.sort_order, CatalogStockStatus.label)
        .all()
    )


@router.get("", response_model=StockStatusListResponse)
def list_stock_statuses(db: Session = Depends(get_db)) -> StockStatusListResponse:
    ensure_default_stock_statuses(db)
    return StockStatusListResponse(data=[StockStatusRead.model_validate(r) for r in _ordered(db)])


@router.post("", response_model=StockStatusResponse, status_code=201)
def create_stock_status(
    payload: StockStatusCreate,
    db: Session = Depends(get_db),
    _: AuthUser = Depends(require_permission("catalog", "create")),
) -> StockStatusResponse:
    ensure_default_stock_statuses(db)
    code = payload.code or slugify_code(payload.label)
    if db.query(CatalogStockStatus).filter(CatalogStockStatus.code == code).first():
        raise HTTPException(status_code=409, detail=f"Stock status '{code}' already exists")

    data = payload.model_dump(exclude={"code"})
    row = CatalogStockStatus(code=code, is_system=False, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return StockStatusResponse(data=StockStatusRead.model_validate(row))


@router.patch("/{status_id}", response_model=StockStatusResponse)
def update_stock_status(
    status_id: str,
    payload: StockStatusUpdate,
    db: Session = Depends(get_db),
    _: AuthUser = Depends(require_permission("catalog", "write")),
) -> StockStatusResponse:
    row = db.get(CatalogStockStatus, status_id)
    if not row:
        raise HTTPException(status_code=404, detail="Stock status not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return StockStatusResponse(data=StockStatusRead.model_validate(row))


@router.delete("/{status_id}")
def delete_stock_status(
    status_id: str,
    db: Session = Depends(get_db),
    _: AuthUser = Depends(require_permission("catalog", "delete")),
) -> dict:
    row = db.get(CatalogStockStatus, status_id)
    if not row:
        raise HTTPException(status_code=404, detail="Stock status not found")
    if row.is_system:
        raise HTTPException(status_code=400, detail="Built-in stock statuses cannot be deleted")

    # Products store the code as plain text, so deleting a status that is still
    # in use would leave those products pointing at nothing.
    in_use = (
        db.query(CatalogProduct)
        .filter(CatalogProduct.stock_status == row.code)
        .count()
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=f"{in_use} product(s) still use '{row.label}'. Move them to another status first, or deactivate this one.",
        )
    db.delete(row)
    db.commit()
    return {"data": {"id": status_id, "deleted": True}, "errors": []}
