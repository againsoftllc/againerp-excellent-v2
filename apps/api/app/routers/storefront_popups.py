from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.catalog_product_special import in_daily_window
from app.models.marketing_happy_hour import MarketingHappyHour
from app.models.marketing_offer import MarketingOffer
from app.models.marketing_popup import MarketingPopup
from app.routers.marketing_popups import popup_paths
from app.routers.storefront_happy_hour import _countdown_iso, _is_public as _happy_hour_public
from app.routers.storefront_offer_pages import _fmt_iso, _is_public as _offer_public

router = APIRouter(tags=["storefront-popups"])


class StorefrontPopup(BaseModel):
    id: str
    # changes whenever the admin edits the popup - a changed popup is shown again even to a visitor who closed the old one
    version: str
    kind: str
    title: str
    body: str
    imageUrl: str = ""
    buttonLabel: str = ""
    href: str = ""
    # a campaign popup counts down: "Ends in:" while it runs, "Starts in:" before the Happy Hour opens
    countdownISO: str = ""
    countdownLabel: str = ""
    delaySeconds: int = 5
    frequency: str = "session"
    frequencyDays: int = 1


class StorefrontPopupResponse(BaseModel):
    data: Optional[StorefrontPopup] = None


def _on_page(row: MarketingPopup, path: str) -> bool:
    if row.pages == "all":
        return True
    if row.pages == "home":
        return path in ("", "/")
    return path in popup_paths(row.paths_json)


def _build(db: Session, row: MarketingPopup, now: datetime) -> Optional[StorefrontPopup]:
    """The popup as shown, or None when what it points at is not running (an ended Happy Hour shows nothing)."""
    base = dict(
        id=row.id,
        version=row.updated_at.isoformat() if row.updated_at else "",
        kind=row.kind,
        title=row.title,
        body=row.body,
        imageUrl=(row.image_url or "").strip(),
        buttonLabel=row.button_label,
        href=row.link_url.strip(),
        delaySeconds=row.delay_seconds,
        frequency=row.frequency,
        frequencyDays=row.frequency_days,
    )
    if row.kind == "happy_hour":
        hh = db.query(MarketingHappyHour).filter(MarketingHappyHour.slug == row.campaign_slug).first()
        if hh is None or not _happy_hour_public(hh, now) or hh.ends_at < now:
            return None
        live = in_daily_window(now, hh.daily_start_hour, hh.daily_end_hour)
        base.update(
            title=row.title or hh.title,
            body=row.body or (hh.subtitle or ""),
            imageUrl=base["imageUrl"],
            buttonLabel=row.button_label or "View deals",
            href=base["href"] or f"/{hh.slug}",
            countdownISO=_countdown_iso(now, hh, live),
            countdownLabel="Ends in:" if live else "Starts in:",
        )
    elif row.kind == "offer":
        offer = db.query(MarketingOffer).filter(MarketingOffer.slug == row.campaign_slug).first()
        if offer is None or not _offer_public(offer, now) or offer.ends_at < now:
            return None
        base.update(
            title=row.title or offer.title,
            body=row.body,
            imageUrl=base["imageUrl"] or (offer.image_url or ""),
            buttonLabel=row.button_label or "View offer",
            href=base["href"] or f"/offers/{offer.slug}",
            countdownISO=_fmt_iso(offer.ends_at) + "Z",
            countdownLabel="Ends in:",
        )
    return StorefrontPopup(**base)


@router.get("/popups", response_model=StorefrontPopupResponse)
def get_popup(
    response: Response,
    db: Session = Depends(get_db),
    path: str = Query("/"),
    device: str = Query("desktop"),
) -> StorefrontPopupResponse:
    """The one popup to show on this page and device right now (highest priority first), or none."""
    response.headers["Cache-Control"] = "public, max-age=30"
    now = datetime.utcnow()
    path = "/" + (path or "/").split("?")[0].strip("/")
    device = "mobile" if device == "mobile" else "desktop"
    rows = (
        db.query(MarketingPopup)
        .filter(MarketingPopup.status == "active")
        .order_by(MarketingPopup.priority.desc(), MarketingPopup.created_at.desc())
        .all()
    )
    for row in rows:
        if row.starts_at and row.starts_at > now:
            continue
        if row.ends_at and row.ends_at < now:
            continue
        if row.devices not in ("all", device) or not _on_page(row, path):
            continue
        popup = _build(db, row, now)
        if popup is not None:
            return StorefrontPopupResponse(data=popup)
    return StorefrontPopupResponse(data=None)
