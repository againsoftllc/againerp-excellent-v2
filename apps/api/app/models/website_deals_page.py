from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.database import Base

DEFAULT_WEBSITE_DEALS_PAGE_ID = "default"

ICON_DIR = "/images/offers/deal-types"

DEFAULT_DEALS_CONTENT: dict[str, Any] = {
    "title": "Excellent Tech Deals",
    "subtitle": "Built for every beat, every space, and every moment.",
    "tabs": [
        {
            "id": "all",
            "label": "Shop All Deals",
            "icon": f"{ICON_DIR}/shop-all-deals.svg",
            "iconActive": f"{ICON_DIR}/shop-all-deals-active.svg",
            "hidden": False,
            "showAll": True,
            "panel": "grid",
            "categorySlugs": [],
            "productSlugs": [],
        },
        {
            "id": "flash-sale",
            "label": "Flash Sale",
            "icon": f"{ICON_DIR}/flash-sale.svg",
            "iconActive": f"{ICON_DIR}/flash-sale-active.svg",
            "hidden": False,
            "showAll": False,
            "panel": "grid",
            "categorySlugs": ["component", "gaming"],
            "productSlugs": [],
        },
        {
            "id": "clearance",
            "label": "Clearance",
            "icon": f"{ICON_DIR}/clearance.svg",
            "iconActive": f"{ICON_DIR}/clearance-active.svg",
            "hidden": False,
            "showAll": False,
            "panel": "grid",
            "categorySlugs": ["monitor", "accessories"],
            "productSlugs": [],
        },
        {
            "id": "study-hard-game-harder",
            "label": "Study Hard",
            "icon": f"{ICON_DIR}/study-hard-game-harder.svg",
            "iconActive": f"{ICON_DIR}/study-hard-game-harder-active.svg",
            "hidden": False,
            "showAll": False,
            "panel": "grid",
            "categorySlugs": ["laptop", "desktops"],
            "productSlugs": [],
        },
        {
            "id": "bundles",
            "label": "Bundles",
            "icon": f"{ICON_DIR}/bundles.svg",
            "iconActive": f"{ICON_DIR}/bundles-active.svg",
            "hidden": False,
            "showAll": False,
            "panel": "bundles",
            "categorySlugs": [],
            "productSlugs": [],
        },
        {
            "id": "coupons",
            "label": "Coupons",
            "icon": f"{ICON_DIR}/coupons.svg",
            "iconActive": f"{ICON_DIR}/coupons-active.svg",
            "hidden": False,
            "showAll": False,
            "panel": "coupons",
            "categorySlugs": ["ups-ips", "security"],
            "productSlugs": [],
        },
    ],
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


def normalize_deals_content(raw: Any) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    tabs_in = src.get("tabs") if isinstance(src.get("tabs"), list) else []
    defaults = DEFAULT_DEALS_CONTENT["tabs"]
    tabs = tabs_in if tabs_in else defaults
    out_tabs = []
    for i, tab in enumerate(tabs):
        row = tab if isinstance(tab, dict) else {}
        panel = row.get("panel")
        if panel not in {"grid", "bundles", "coupons"}:
            panel = "grid"
        out_tabs.append(
            {
                "id": str(row.get("id") or f"tab-{i}"),
                "label": str(row.get("label") or f"Tab {i + 1}"),
                "icon": str(row.get("icon") or ""),
                "iconActive": str(row.get("iconActive") or ""),
                "hidden": bool(row.get("hidden")),
                "showAll": bool(row.get("showAll")),
                "panel": panel,
                "categorySlugs": [str(x) for x in (row.get("categorySlugs") or []) if str(x).strip()],
                "productSlugs": [str(x) for x in (row.get("productSlugs") or []) if str(x).strip()],
            }
        )
    title = str(src.get("title") or "").strip() or DEFAULT_DEALS_CONTENT["title"]
    subtitle = src.get("subtitle")
    return {
        "title": title,
        "subtitle": subtitle if isinstance(subtitle, str) else DEFAULT_DEALS_CONTENT["subtitle"],
        "tabs": out_tabs,
    }


# Empty Flash / Clearance / Study tabs get these catalog roots (and their children).
TAB_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "flash-sale": ("component", "gaming"),
    "clearance": ("monitor", "accessories", "gadget", "mobile-accessories"),
    "study-hard-game-harder": ("laptop", "desktops"),
}


def _flatten_category_slugs(nodes: list[Any]) -> list[str]:
    out: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        slug = str(node.get("slug") or "").strip()
        if slug:
            out.append(slug)
        children = node.get("children")
        if isinstance(children, list):
            out.extend(_flatten_category_slugs(children))
    return out


def fill_empty_deals_from_catalog(db: Session, content: dict[str, Any]) -> dict[str, Any]:
    """Assign live catalog categories + product slugs to deal tabs that have none."""
    tabs_in = content.get("tabs")
    if not isinstance(tabs_in, list):
        return content
    needs = [
        tab
        for tab in tabs_in
        if isinstance(tab, dict)
        and tab.get("panel") not in {"bundles", "coupons"}
        and not tab.get("showAll")
        and not (tab.get("categorySlugs") or tab.get("productSlugs"))
    ]
    if not needs:
        return content
    try:
        from app.services.ecommerce.storefront_catalog_service import StorefrontCatalogService

        catalog = StorefrontCatalogService(db)
        known = set(_flatten_category_slugs(catalog.list_categories(channel="catalog")))
    except Exception:
        return content

    tabs_out: list[Any] = []
    changed = False
    for tab in tabs_in:
        if not isinstance(tab, dict):
            tabs_out.append(tab)
            continue
        row = dict(tab)
        if (
            row.get("panel") in {"bundles", "coupons"}
            or row.get("showAll")
            or (row.get("categorySlugs") or row.get("productSlugs"))
        ):
            tabs_out.append(row)
            continue
        hints = TAB_CATEGORY_HINTS.get(str(row.get("id") or ""), ())
        roots = [slug for slug in hints if slug in known]
        row["categorySlugs"] = roots
        product_slugs: list[str] = []
        try:
            for cat in roots:
                if len(product_slugs) >= 16:
                    break
                result = catalog.list_products(category_slug=cat, per_page=16, page=1)
                for item in result.items:
                    slug = (getattr(item, "slug", None) or "").strip()
                    if slug and slug not in product_slugs:
                        product_slugs.append(slug)
                    if len(product_slugs) >= 16:
                        break
        except Exception:
            product_slugs = product_slugs
        row["productSlugs"] = product_slugs
        changed = True
        tabs_out.append(row)
    if not changed:
        return content
    return {**content, "tabs": tabs_out}


class WebsiteDealsPage(Base):
    """Singleton Excellent Tech Deals page (tabs on /offers-and-deals)."""

    __tablename__ = "website_deals_page"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=DEFAULT_WEBSITE_DEALS_PAGE_ID)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    content_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


def ensure_website_deals_page(db: Session) -> WebsiteDealsPage:
    row = db.get(WebsiteDealsPage, DEFAULT_WEBSITE_DEALS_PAGE_ID)
    if not row:
        row = WebsiteDealsPage(
            id=DEFAULT_WEBSITE_DEALS_PAGE_ID,
            content_json=dump_json(DEFAULT_DEALS_CONTENT),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    content = normalize_deals_content(load_json(row.content_json))
    filled = normalize_deals_content(fill_empty_deals_from_catalog(db, content))
    if dump_json(filled) != dump_json(content):
        row.content_json = dump_json(filled)
        db.commit()
        db.refresh(row)
    return row
