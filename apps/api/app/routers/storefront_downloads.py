"""Public, token-secured download link for a paid order's digital files.

No login required — the token itself is the secret (unguessable, one per
order+file, see digital_delivery_service.grant_downloads_for_order). This is
what the confirmation email links to, and what the account Downloads page's
buttons point at.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.catalog_product_digital_file import CatalogProductDigitalFile
from app.models.commerce_order import CommerceOrder
from app.models.commerce_order_digital_download import CommerceOrderDigitalDownload

router = APIRouter(prefix="/downloads", tags=["storefront-downloads"])


@router.get("/{token}")
def download_digital_file(token: str, db: Session = Depends(get_db)):
    grant = (
        db.query(CommerceOrderDigitalDownload)
        .filter(CommerceOrderDigitalDownload.token == token)
        .first()
    )
    if not grant:
        raise HTTPException(status_code=404, detail="Download link not found")

    order = db.get(CommerceOrder, grant.order_id)
    if not order or order.payment_status != "paid":
        raise HTTPException(status_code=403, detail="This order has not been paid")

    if grant.expires_at and datetime.utcnow() > grant.expires_at:
        raise HTTPException(status_code=410, detail="This download link has expired")
    if grant.max_downloads is not None and grant.download_count >= grant.max_downloads:
        raise HTTPException(status_code=403, detail="Download limit reached for this link")

    digital_file = db.get(CatalogProductDigitalFile, grant.digital_file_id)
    if not digital_file or not Path(digital_file.storage_path).exists():
        raise HTTPException(status_code=404, detail="File no longer available")

    grant.download_count = (grant.download_count or 0) + 1
    db.commit()

    return FileResponse(
        path=digital_file.storage_path,
        filename=digital_file.file_name,
        media_type=digital_file.mime_type or "application/octet-stream",
    )
