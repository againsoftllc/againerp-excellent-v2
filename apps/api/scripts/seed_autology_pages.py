"""Seed Autology information pages into Website Pages, and drop demo CMS pages.

Source is the same storefront export the catalog seeder reads, so the shop's
information pages and the admin Website module stay in step:

    curl http://localhost:3002/api/dev/catalog-export
      > apps/api/scripts/data/autology_catalog.json

Footer Important Links on the shop read published Website Pages
(GET /storefront/pages) plus a custom Brands link.

Usage (API container):

    python scripts/seed_autology_pages.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.database import SessionLocal
from app.models.website_page import WebsitePage, dump_json, load_json
from app.models.workspace_site import WorkspaceSite
from app.services.seed_once import already_seeded, mark_seeded
from app.services.footer_links_sync import sync_footer_links_bundle

DATA_PATH = Path(__file__).resolve().parent / "data" / "excellent_catalog.json"

SITE_NAME = "Excellent Technology BD"

# Demo pages shipped with the base seed that Autology does not use. "pg-about"
# is the base seed's own generic About Us page — it happens to use the exact
# id Autology's "about-us" page also resolves to (`_page_id`), so it has to be
# gone *before* the upsert loop below runs, or that loop finds a page already
# there and — correctly, since it never overwrites an existing page — leaves
# the base's generic copy in place instead of Autology's own.
DELETE_PAGE_IDS = ("pg-summer", "pg-shop", "pg-about")

KEEP_SYSTEM_IDS = (
    "pg-home",
    "pg-cart",
    "pg-checkout",
    "pg-category",
    "pg-order-track",
)

SCHEMA_BY_SLUG = {
    "about-us": "AboutPage",
    "contact-us": "ContactPage",
    "privacy-policy": "WebPage",
    "terms-and-conditions": "WebPage",
}


def _esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _block_html(block: dict) -> str:
    """Render one storefront information block as CMS-editable HTML."""
    kind = block.get("type")
    if kind in ("h2", "h3", "h4"):
        return f"<{kind}>{_esc(block.get('text'))}</{kind}>"
    if kind == "p":
        return f"<p>{_esc(block.get('text'))}</p>"
    if kind == "note":
        return f"<blockquote><p>{_esc(block.get('text'))}</p></blockquote>"
    if kind == "ul":
        items = "".join(f"<li>{_esc(i)}</li>" for i in block.get("items") or [])
        return f"<ul>{items}</ul>" if items else ""
    if kind == "checklist":
        items = "".join(
            f"<li><strong>{_esc(i.get('title'))}</strong> — {_esc(i.get('text'))}</li>"
            for i in block.get("items") or []
        )
        return f"<ul>{items}</ul>" if items else ""
    if kind == "contact":
        rows = ""
        for entry in block.get("items") or []:
            value = _esc(entry.get("value"))
            href = entry.get("href")
            cell = f'<a href="{_esc(href)}">{value}</a>' if href else value
            rows += f"<tr><th>{_esc(entry.get('label'))}</th><td>{cell}</td></tr>"
        return f"<table><tbody>{rows}</tbody></table>" if rows else ""
    if kind == "table":
        head = "".join(f"<th>{_esc(h)}</th>" for h in block.get("head") or [])
        body = "".join(
            "<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>"
            for row in block.get("rows") or []
        )
        thead = f"<thead><tr>{head}</tr></thead>" if head else ""
        return f"<table>{thead}<tbody>{body}</tbody></table>" if body else ""
    # Unknown block kinds keep their text rather than vanishing from the page.
    text = block.get("text")
    return f"<p>{_esc(text)}</p>" if text else ""


def _page_html(page: dict) -> str:
    """Body only — the lead paragraph is the page description, not a body block.

    The storefront renders the intro in the page header, so inlining it here too
    would print it twice.
    """
    parts: list[str] = []
    for block in page.get("content") or []:
        html = _block_html(block)
        if html:
            parts.append(html)
    return "\n".join(parts)


def _page_id(slug: str) -> str:
    return f"pg-{slug}"


def _is_live(page: dict) -> bool:
    """Storefront pages carry `status` as a boolean flag, not a state string."""
    status = page.get("status")
    if isinstance(status, bool):
        return status
    if isinstance(status, str):
        return status.strip().lower() in ("active", "published", "true", "1")
    return True


def _seo(page: dict) -> dict:
    return {
        "meta_title": page.get("metaTitle") or f"{page['title']} | {SITE_NAME}",
        "meta_description": page.get("metaDescription") or page.get("intro") or "",
        "canonical_url": f"/{page['slug']}",
        "robots": "index,follow",
        "schema_type": SCHEMA_BY_SLUG.get(page["slug"], "WebPage"),
    }


def _free_slug(db, slug: str, keep_id: str) -> None:
    """Rename any other page holding this slug — `website_pages.slug` is unique."""
    clash = (
        db.query(WebsitePage)
        .filter(WebsitePage.slug == slug, WebsitePage.id != keep_id)
        .first()
    )
    if clash is not None:
        clash.slug = f"{slug}-old-{clash.id}"
        clash.url = f"/{clash.slug}"
        db.flush()


def _claim_slug(db, row: WebsitePage, slug: str) -> None:
    _free_slug(db, slug, row.id)
    row.slug = slug
    row.url = f"/{slug}"


def _upsert_page(db, page: dict) -> bool:
    """Create the page if the DB doesn't have it yet.

    Insert-only: this boots on every API start, and once a page exists the
    admin's Website → Pages editor owns its body, SEO and status — overwriting
    it here on every restart would revert whatever was last saved there.
    Returns whether a new page was created.
    """
    page_id = _page_id(page["slug"])
    if db.get(WebsitePage, page_id) is not None:
        return False
    if db.query(WebsitePage).filter(WebsitePage.slug == page["slug"]).first() is not None:
        return False

    now = datetime.utcnow()
    _free_slug(db, page["slug"], page_id)
    row = WebsitePage(
        id=page_id,
        company_id="default",
        name=page["title"],
        slug=page["slug"],
        url=f"/{page['slug']}",
        language="en",
        layout="default",
        template="Default",
        page_type="website",
        creator="Admin",
        created_at=now,
    )
    db.add(row)
    db.flush()

    _claim_slug(db, row, page["slug"])
    # `description` is the lead paragraph the storefront prints under the page
    # title; the meta description lives in seo_json.
    row.description = (page.get("intro") or page.get("metaDescription") or "")[:500]
    row.body_html = _page_html(page)
    row.visibility = "public"
    row.status = "published" if _is_live(page) else "draft"
    row.seo_status = "complete"
    row.updated_by = "Admin"
    row.published_at = now
    row.updated_at = now
    row.seo_json = dump_json(_seo(page))
    row.flags_json = dump_json(
        {
            "is_home": False,
            "is_system": False,
            "is_locked": False,
            "slug_locked": False,
            "delete_disabled": False,
        }
    )
    return True


def _delete_unused(db) -> list[str]:
    removed = []
    for page_id in DELETE_PAGE_IDS:
        row = db.get(WebsitePage, page_id)
        if row is not None:
            db.delete(row)
            removed.append(page_id)
    return removed


def _prune_stale(db, keep_slugs: set[str]) -> list[str]:
    """Drop leftover CMS pages not in ``keep_slugs``. Not called automatically —
    an admin-created page has a slug this bundled list will never contain, so
    running this on every boot would delete it."""
    removed = []
    rows = db.query(WebsitePage).filter(WebsitePage.page_type == "website").all()
    for row in rows:
        if row.id in KEEP_SYSTEM_IDS or row.slug in keep_slugs:
            continue
        flags = load_json(row.flags_json, {})
        if isinstance(flags, dict) and (flags.get("is_system") or flags.get("is_home")):
            continue
        db.delete(row)
        removed.append(row.slug or row.id)
    return removed


def _footer_links(pages: list[dict]) -> list[dict]:
    """Footer "Information" column, in the storefront's own page order."""
    ordered = sorted(pages, key=lambda p: (int(p.get("sortOrder") or 0), p["slug"]))
    links = [
        {
            "id": _page_id(page["slug"]),
            "label": page["title"],
            "href": f"/{page['slug']}",
            "hidden": not _is_live(page),
        }
        for page in ordered
    ]
    # Brands is a storefront route, not a CMS page, but belongs in the column.
    links.append({"id": "brands", "label": "Brands", "href": "/brands", "hidden": False})
    return links


def load_pages() -> list[dict]:
    if not DATA_PATH.exists():
        raise SystemExit(
            f"Missing {DATA_PATH} — export it from the storefront first:\n"
            "  curl http://localhost:3002/api/dev/catalog-export "
            "> apps/api/scripts/data/autology_catalog.json"
        )
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return payload.get("information_pages") or []


def main() -> None:
    pages = load_pages()
    db = SessionLocal()
    try:
        slugs = [p.get("slug") for p in pages if p.get("slug")]
        has_data = bool(slugs) and db.query(WebsitePage).filter(WebsitePage.slug.in_(slugs)).first() is not None
        if already_seeded(db, "excellent_pages_seeded", has_data=has_data):
            print(f"{SITE_NAME} pages already seeded; skipping.")
            return
        # Demo pages first — "pg-about" collides with Autology's own id, so it
        # has to be gone before the upsert loop checks whether that page exists.
        removed = _delete_unused(db)
        db.flush()

        created = sum(1 for page in pages if _upsert_page(db, page))
        db.flush()

        # Only touch the footer's link column when this run actually added a
        # page to link — otherwise this would overwrite any reordering an
        # admin did in Website → Footer on every boot.
        if created:
            site = db.query(WorkspaceSite).filter(WorkspaceSite.is_primary.is_(True)).first()
            if site is not None:
                sync_footer_links_bundle(
                    db,
                    site,
                    _footer_links(pages),
                    information_title="Information",
                )

        mark_seeded(db, "excellent_pages_seeded")
        db.commit()
        print(
            f"Pages created={created} already_existed={len(pages) - created} "
            f"demo_removed={removed}"
        )
        print(f"{SITE_NAME} page seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
