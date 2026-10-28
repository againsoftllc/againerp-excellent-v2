from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import require_write_access
from app.models.website_hot_products import (
    dump_json,
    ensure_website_hot_products,
    load_json,
    normalize_hot_products_content,
)
from app.schemas.website_hot_products import (
    HotProductsContent,
    WebsiteHotProductsRead,
    WebsiteHotProductsResponse,
    WebsiteHotProductsUpdate,
)

router = APIRouter(prefix="/hot-products", tags=["website-hot-products"])


def _to_read(row) -> WebsiteHotProductsRead:
    content = HotProductsContent.model_validate(normalize_hot_products_content(load_json(row.content_json)))
    return WebsiteHotProductsRead(
        id=row.id,
        company_id=row.company_id,
        content=content,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=WebsiteHotProductsResponse)
def get_hot_products(db: Session = Depends(get_db)) -> WebsiteHotProductsResponse:
    row = ensure_website_hot_products(db)
    return WebsiteHotProductsResponse(data=_to_read(row))


@router.patch("", response_model=WebsiteHotProductsResponse)
def update_hot_products(
    payload: WebsiteHotProductsUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> WebsiteHotProductsResponse:
    row = ensure_website_hot_products(db)
    row.content_json = dump_json(normalize_hot_products_content(payload.content.model_dump()))
    db.commit()
    db.refresh(row)
    return WebsiteHotProductsResponse(data=_to_read(row))
