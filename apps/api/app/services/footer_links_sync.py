"""Keep footer information links in sync across CMS, menu, and site options."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.website_menu import SYSTEM_MENU_FOOTER_ID, WebsiteMenu
from app.models.workspace_site import WorkspaceSite
from app.services.site_store_options import dump_site_options, load_site_options
from app.services.storefront_site_options import STOREFRONT_OPTIONS_KEY, build_storefront_options


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def cms_links_to_options_links(links: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in links:
        if not isinstance(row, dict):
            continue
        label = _text(row.get("label")) or _text(row.get("name"))
        href = _text(row.get("href"))
        if not label or not href:
            continue
        out.append(
            {
                "id": _text(row.get("id")) or f"link-{uuid.uuid4().hex[:8]}",
                "label": label,
                "href": href if href.startswith("/") else f"/{href.lstrip('/')}",
                "hidden": bool(row.get("hidden")),
                "page_id": _text(row.get("pageId") or row.get("page_id")) or None,
                "link_type": "page" if row.get("pageId") or row.get("page_id") else "custom",
            }
        )
    return out


def cms_footer_to_options_links(footer: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Prefer two-column links, then canonical footer.links."""
    if not isinstance(footer, dict):
        return []
    combined: list[Any] = []
    for key in ("linksCol1", "linksCol2"):
        rows = footer.get(key)
        if isinstance(rows, list):
            combined.extend(rows)
    from_cols = cms_links_to_options_links(combined)
    if from_cols:
        return from_cols
    cms_links = footer.get("links")
    if isinstance(cms_links, list):
        return cms_links_to_options_links(cms_links)
    return []


def menu_items_to_options_links(items: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        label = _text(row.get("label"))
        href = _text(row.get("href"))
        if not label or not href:
            continue
        out.append(
            {
                "id": _text(row.get("id")) or f"link-{uuid.uuid4().hex[:8]}",
                "label": label,
                "href": href if href.startswith("/") else f"/{href.lstrip('/')}",
                "hidden": bool(row.get("hidden")),
                "page_id": _text(row.get("link_ref_id")) or None,
                "link_type": _text(row.get("link_type")) or "custom",
            }
        )
    return out


def options_links_to_menu_items(links: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in links:
        if not isinstance(row, dict):
            continue
        label = _text(row.get("label"))
        href = _text(row.get("href"))
        if not label or not href:
            continue
        link_type = _text(row.get("link_type")) or "custom"
        page_id = row.get("page_id")
        out.append(
            {
                "id": _text(row.get("id")) or f"fi-{uuid.uuid4().hex[:8]}",
                "label": label,
                "link_type": link_type if link_type in ("page", "category", "brand", "custom") else "custom",
                "link_ref_id": _text(page_id) or None,
                "href": href,
                "hidden": bool(row.get("hidden")),
                "children": [],
            }
        )
    return out


def options_links_to_cms_links(links: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in links:
        if not isinstance(row, dict):
            continue
        label = _text(row.get("label"))
        href = _text(row.get("href"))
        if not label or not href:
            continue
        cms: dict[str, Any] = {
            "id": _text(row.get("id")) or f"link-{uuid.uuid4().hex[:8]}",
            "label": label,
            "href": href,
            "hidden": bool(row.get("hidden")),
        }
        page_id = _text(row.get("page_id"))
        if page_id:
            cms["pageId"] = page_id
        out.append(cms)
    return out


def apply_footer_links_to_site_options(
    site: WorkspaceSite,
    links: list[dict[str, Any]],
    *,
    information_title: Optional[str] = None,
) -> None:
    options = load_site_options(getattr(site, "options_json", None))
    storefront = build_storefront_options(options)
    storefront["footer"]["links"] = links
    if information_title is not None:
        title = _text(information_title)
        if title:
            storefront["footer"]["information_title"] = title
    options[STOREFRONT_OPTIONS_KEY] = storefront
    site.options_json = dump_site_options(options)


def sync_footer_menu_from_links(db: Session, links: list[dict[str, Any]]) -> None:
    menu = db.get(WebsiteMenu, SYSTEM_MENU_FOOTER_ID)
    if not menu:
        return
    menu.items_json = json.dumps(options_links_to_menu_items(links), ensure_ascii=False)


def sync_site_cms_footer_links(
    site: WorkspaceSite,
    links: list[dict[str, Any]],
    *,
    information_title: Optional[str] = None,
) -> None:
    raw = getattr(site, "storefront_cms_json", None) or ""
    try:
        data = json.loads(raw) if raw and str(raw).strip() else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    footer = data.get("footer") if isinstance(data.get("footer"), dict) else {}
    cms_links = options_links_to_cms_links(links)
    footer["links"] = cms_links
    visible = [row for row in cms_links if not row.get("hidden")]
    split_at = 3 if len(visible) >= 6 else max((len(visible) + 1) // 2, 0)

    def _col(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "id": _text(row.get("id")),
                "name": _text(row.get("label")),
                "href": _text(row.get("href")),
                "hidden": bool(row.get("hidden")),
            }
            for row in rows
        ]

    footer["linksCol1"] = _col(visible[:split_at])
    footer["linksCol2"] = _col(visible[split_at:])
    if information_title is not None:
        title = _text(information_title)
        if title:
            footer["informationTitle"] = title
            footer["linksTitle"] = title
    data["footer"] = footer
    site.storefront_cms_json = json.dumps(data, ensure_ascii=False)


def sync_all_sites_footer_links_from_menu(db: Session, items: list[Any]) -> None:
    links = menu_items_to_options_links(items)
    sites = db.query(WorkspaceSite).all()
    for site in sites:
        apply_footer_links_to_site_options(site, links)
        sync_site_cms_footer_links(site, links)


def sync_footer_links_bundle(
    db: Session,
    site: WorkspaceSite,
    links: list[dict[str, Any]],
    *,
    information_title: Optional[str] = None,
) -> None:
    """Write the same link list to site options, CMS JSON, and the footer menu."""
    apply_footer_links_to_site_options(site, links, information_title=information_title)
    sync_site_cms_footer_links(site, links, information_title=information_title)
    sync_footer_menu_from_links(db, links)


def resolve_footer_information_title(site: WorkspaceSite) -> str:
    options = load_site_options(getattr(site, "options_json", None))
    storefront = build_storefront_options(options)
    title = _text(storefront.get("footer", {}).get("information_title"))
    if title:
        return title
    raw = getattr(site, "storefront_cms_json", None) or ""
    try:
        data = json.loads(raw) if raw and str(raw).strip() else {}
    except json.JSONDecodeError:
        data = {}
    footer = data.get("footer") if isinstance(data.get("footer"), dict) else {}
    return _text(footer.get("informationTitle") or footer.get("information_title"))


def resolve_footer_links_for_site(
    site: WorkspaceSite,
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    """Canonical footer links: site options, then CMS JSON, then footer menu."""
    options = load_site_options(getattr(site, "options_json", None))
    storefront = build_storefront_options(options)
    links = storefront.get("footer", {}).get("links") or []
    if links:
        return links

    raw = getattr(site, "storefront_cms_json", None) or ""
    try:
        data = json.loads(raw) if raw and str(raw).strip() else {}
    except json.JSONDecodeError:
        data = {}
    footer = data.get("footer") if isinstance(data.get("footer"), dict) else {}
    resolved = cms_footer_to_options_links(footer)
    if resolved:
        return resolved

    if db is not None:
        menu = db.get(WebsiteMenu, SYSTEM_MENU_FOOTER_ID)
        if menu and menu.items_json:
            try:
                items = json.loads(menu.items_json)
            except json.JSONDecodeError:
                items = []
            if isinstance(items, list) and items:
                resolved = menu_items_to_options_links(items)
                if resolved:
                    return resolved

    return []


def enrich_site_options_footer_links(
    db: Session,
    site: WorkspaceSite,
    options: dict[str, Any] | None,
) -> dict[str, Any]:
    """Expose CMS/menu footer links in admin when options snapshot is still empty."""
    merged = dict(options or {})
    storefront = build_storefront_options(merged)
    if storefront.get("footer", {}).get("links"):
        return merged

    links = resolve_footer_links_for_site(site, db)
    if not links:
        return merged

    sf = dict(merged.get(STOREFRONT_OPTIONS_KEY) or {})
    footer = dict(sf.get("footer") or {})
    footer["links"] = links
    if not _text(footer.get("information_title")):
        title = resolve_footer_information_title(site)
        if title:
            footer["information_title"] = title
    sf["footer"] = footer
    merged[STOREFRONT_OPTIONS_KEY] = sf
    return merged
