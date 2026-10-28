from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import require_write_access
from app.models.website_deals_page import (
    dump_json,
    ensure_website_deals_page,
    load_json,
    normalize_deals_content,
)
from app.schemas.website_deals import (
    DealsPageContent,
    WebsiteDealsPageRead,
    WebsiteDealsPageResponse,
    WebsiteDealsPageUpdate,
)

router = APIRouter(prefix="/deals-page", tags=["website-deals"])


def _to_read(row) -> WebsiteDealsPageRead:
    content = DealsPageContent.model_validate(normalize_deals_content(load_json(row.content_json)))
    return WebsiteDealsPageRead(
        id=row.id,
        company_id=row.company_id,
        content=content,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=WebsiteDealsPageResponse)
def get_deals_page(db: Session = Depends(get_db)) -> WebsiteDealsPageResponse:
    row = ensure_website_deals_page(db)
    return WebsiteDealsPageResponse(data=_to_read(row))


@router.patch("", response_model=WebsiteDealsPageResponse)
def update_deals_page(
    payload: WebsiteDealsPageUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> WebsiteDealsPageResponse:
    row = ensure_website_deals_page(db)
    row.content_json = dump_json(normalize_deals_content(payload.content.model_dump()))
    db.commit()
    db.refresh(row)
    return WebsiteDealsPageResponse(data=_to_read(row))
