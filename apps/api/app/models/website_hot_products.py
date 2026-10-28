from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.database import Base

DEFAULT_WEBSITE_HOT_PRODUCTS_ID = "default"

DEFAULT_HOT_TABS: list[dict[str, Any]] = [
    {
        "id": "all",
        "label": "All",
        "hidden": False,
        "showAll": True,
        "categorySlugs": [],
        "productSlugs": [],
    },
]

DEFAULT_HOT_PRODUCTS_CONTENT: dict[str, Any] = {
    "title": "Hot Products",
    "subtitle": "Built for every beat, every space, and every moment.",
    "bannerUrl": "",
    "tabs": DEFAULT_HOT_TABS,
}


def dump_json(value: Any) -> str:
    return json.dumps(value if value is not None else {})


def load_json(value: Optional[str], default: Any = None) -> Any:
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default if default is not None else {}


def _unique_slugs(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        slug = str(item).strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append(slug)
    return out


def normalize_hot_products_content(raw: Any) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    legacy_slugs = _unique_slugs(src.get("productSlugs"))
    tabs_in = src.get("tabs") if isinstance(src.get("tabs"), list) else []
    tabs: list[dict[str, Any]] = []
    for i, tab in enumerate(tabs_in):
        row = tab if isinstance(tab, dict) else {}
        tabs.append(
            {
                "id": str(row.get("id") or f"tab-{i}"),
                "label": str(row.get("label") or f"Tab {i + 1}"),
                "hidden": bool(row.get("hidden")),
                "showAll": bool(row.get("showAll")),
                "categorySlugs": _unique_slugs(row.get("categorySlugs")),
                "productSlugs": _unique_slugs(row.get("productSlugs")),
            }
        )
    if not tabs:
        tabs = [dict(item) for item in DEFAULT_HOT_TABS]
        if legacy_slugs:
            tabs.append(
                {
                    "id": "hot",
                    "label": "Hot",
                    "hidden": False,
                    "showAll": False,
                    "categorySlugs": [],
                    "productSlugs": legacy_slugs,
                }
            )
    title = str(src.get("title") or "").strip() or DEFAULT_HOT_PRODUCTS_CONTENT["title"]
    subtitle = src.get("subtitle")
    banner = src.get("bannerUrl")
    return {
        "title": title,
        "subtitle": subtitle if isinstance(subtitle, str) else DEFAULT_HOT_PRODUCTS_CONTENT["subtitle"],
        "bannerUrl": banner.strip() if isinstance(banner, str) else "",
        "tabs": tabs,
    }


class WebsiteHotProducts(Base):
    """Singleton Hot Products page (banner + tabs on /hot-products)."""

    __tablename__ = "website_hot_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=DEFAULT_WEBSITE_HOT_PRODUCTS_ID)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    content_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


def ensure_website_hot_products(db: Session) -> WebsiteHotProducts:
    row = db.get(WebsiteHotProducts, DEFAULT_WEBSITE_HOT_PRODUCTS_ID)
    if not row:
        row = WebsiteHotProducts(
            id=DEFAULT_WEBSITE_HOT_PRODUCTS_ID,
            content_json=dump_json(DEFAULT_HOT_PRODUCTS_CONTENT),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    content = normalize_hot_products_content(load_json(row.content_json))
    if dump_json(content) != (row.content_json or ""):
        row.content_json = dump_json(content)
        db.commit()
        db.refresh(row)
    return row
