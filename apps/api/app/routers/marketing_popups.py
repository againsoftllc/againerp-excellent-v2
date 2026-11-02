from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import require_write_access
from app.models.marketing_popup import MarketingPopup
from app.schemas.marketing_popup import PopupListResponse, PopupRead, PopupResponse, PopupUpdate, PopupWrite

router = APIRouter(prefix="/marketing/popups", tags=["marketing-popups"])


def popup_paths(raw: str | None) -> List[str]:
    try:
        data = json.loads(raw or "[]")
    except ValueError:
        return []
    return [str(p).strip() for p in data if str(p).strip()] if isinstance(data, list) else []


def _clean_paths(paths: List[str]) -> str:
    out: List[str] = []
    for p in paths:
        p = (p or "").strip()
        if not p:
            continue
        p = "/" + p.lstrip("/")
        if p not in out:
            out.append(p[:200])
    return json.dumps(out)


def _read(row: MarketingPopup) -> PopupRead:
    return PopupRead(
        id=row.id, name=row.name, kind=row.kind, status=row.status, title=row.title, body=row.body,
        image_url=row.image_url, button_label=row.button_label, link_url=row.link_url,
        campaign_slug=row.campaign_slug, starts_at=row.starts_at, ends_at=row.ends_at,
        delay_seconds=row.delay_seconds, frequency=row.frequency, frequency_days=row.frequency_days,
        pages=row.pages, paths=popup_paths(row.paths_json), devices=row.devices, priority=row.priority,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _check(data: dict) -> None:
    kind = data.get("kind")
    if kind in ("happy_hour", "offer") and not (data.get("campaign_slug") or "").strip():
        raise HTTPException(status_code=400, detail="Pick the Happy Hour / Offer this popup shows")
    if kind == "image" and not (data.get("image_url") or "").strip():
        raise HTTPException(status_code=400, detail="An image popup needs a picture")
    if data.get("starts_at") and data.get("ends_at") and data["ends_at"] < data["starts_at"]:
        raise HTTPException(status_code=400, detail="The end must be after the start")


@router.get("", response_model=PopupListResponse)
def list_popups(db: Session = Depends(get_db)) -> PopupListResponse:
    rows = db.query(MarketingPopup).order_by(MarketingPopup.priority.desc(), MarketingPopup.created_at.desc()).all()
    return PopupListResponse(data=[_read(r) for r in rows])


@router.get("/{popup_id}", response_model=PopupResponse)
def get_popup(popup_id: str, db: Session = Depends(get_db)) -> PopupResponse:
    row = db.get(MarketingPopup, popup_id)
    if not row:
        raise HTTPException(status_code=404, detail="Popup not found")
    return PopupResponse(data=_read(row))


@router.post("", response_model=PopupResponse, status_code=201)
def create_popup(payload: PopupWrite, db: Session = Depends(get_db), _: object = Depends(require_write_access)) -> PopupResponse:
    data = payload.model_dump()
    _check(data)
    paths = data.pop("paths")
    row = MarketingPopup(**data, paths_json=_clean_paths(paths))
    db.add(row)
    db.commit()
    db.refresh(row)
    return PopupResponse(data=_read(row))


@router.patch("/{popup_id}", response_model=PopupResponse)
def update_popup(popup_id: str, payload: PopupUpdate, db: Session = Depends(get_db), _: object = Depends(require_write_access)) -> PopupResponse:
    row = db.get(MarketingPopup, popup_id)
    if not row:
        raise HTTPException(status_code=404, detail="Popup not found")
    data = payload.model_dump(exclude_unset=True)
    paths = data.pop("paths", None)
    merged = {**{c: getattr(row, c) for c in ("kind", "campaign_slug", "image_url", "starts_at", "ends_at")}, **data}
    _check(merged)
    for key, value in data.items():
        setattr(row, key, value)
    if paths is not None:
        row.paths_json = _clean_paths(paths)
    db.commit()
    db.refresh(row)
    return PopupResponse(data=_read(row))


@router.delete("/{popup_id}", status_code=204)
def delete_popup(popup_id: str, db: Session = Depends(get_db), _: object = Depends(require_write_access)) -> None:
    row = db.get(MarketingPopup, popup_id)
    if not row:
        raise HTTPException(status_code=404, detail="Popup not found")
    db.delete(row)
    db.commit()
