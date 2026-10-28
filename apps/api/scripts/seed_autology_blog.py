"""Seed the Autology blog (categories and posts) from the storefront export.

Insert-only, and meant to run once: it creates the shop's own articles so the
blog the admin edits is the blog the storefront shows, then leaves every row
alone from then on — see the docstrings on `seed_categories` and `seed_posts`.

Body content is written as HTML; the storefront converts it back into the
blocks its article layout renders, the same way information pages work.

Source:

    curl http://localhost:3002/api/dev/catalog-export
      > apps/api/scripts/data/autology_catalog.json

Usage (API container):

    python scripts/seed_autology_blog.py
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import scripts.init_db  # noqa: F401 — registers every ORM model before mapping
from app.database import SessionLocal
from app.models.blog_category import BlogCategory
from app.models.blog_post import BlogPost
from app.services.seed_once import already_seeded, mark_seeded

DATA_PATH = Path(__file__).resolve().parent / "data" / "excellent_catalog.json"


def _esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _block_html(block: dict) -> str:
    kind = block.get("type")
    if kind in ("h2", "h3", "h4"):
        return f"<{kind}>{_esc(block.get('text'))}</{kind}>"
    if kind == "p":
        return f"<p>{_esc(block.get('text'))}</p>"
    if kind == "note":
        return f"<blockquote><p>{_esc(block.get('text'))}</p></blockquote>"
    if kind in ("ul", "ol"):
        items = "".join(f"<li>{_esc(i)}</li>" for i in block.get("items") or [])
        return f"<{kind}>{items}</{kind}>" if items else ""
    if kind == "table":
        head = "".join(f"<th>{_esc(h)}</th>" for h in block.get("head") or [])
        body = "".join(
            "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
            for row in block.get("rows") or []
        )
        thead = f"<thead><tr>{head}</tr></thead>" if head else ""
        return f"<table>{thead}<tbody>{body}</tbody></table>" if body else ""
    text = block.get("text")
    return f"<p>{_esc(text)}</p>" if text else ""


def _post_html(post: dict) -> str:
    return "\n".join(
        html for html in (_block_html(b) for b in post.get("content") or []) if html
    )


def _parse_date(value: str | None) -> datetime | None:
    """`12 Aug, 2026` → datetime."""
    if not value:
        return None
    for fmt in ("%d %b, %Y", "%d %B, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def load_blog() -> dict:
    if not DATA_PATH.exists():
        raise SystemExit(
            f"Missing {DATA_PATH} — export it from the storefront first:\n"
            "  curl http://localhost:3002/api/dev/catalog-export "
            "> apps/api/scripts/data/autology_catalog.json"
        )
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return payload.get("blog") or {}


def seed_categories(db, rows: list[dict]) -> dict[str, BlogCategory]:
    """Create any blog category the storefront defines but the DB doesn't have
    yet, and return every known category by slug so `seed_posts` can resolve
    each post's category.

    Insert-only: this boots on every API start, and once a category exists the
    admin's Blog → Categories screen owns its name, description and order.
    """
    by_slug = {c.slug: c for c in db.query(BlogCategory).all()}
    created = 0

    for order, item in enumerate(rows):
        slug = (item.get("slug") or "").strip()
        if not slug or slug in by_slug:
            continue
        row = BlogCategory(
            id=str(uuid.uuid4()),
            slug=slug,
            name=item.get("name") or slug,
            description=item.get("description") or "",
            status="active",
            sort_order=order,
        )
        db.add(row)
        by_slug[slug] = row
        created += 1

    db.flush()
    print(f"Blog categories created={created} already_existed={len(by_slug) - created}")
    return by_slug


def seed_posts(db, rows: list[dict], categories: dict[str, BlogCategory]) -> int:
    """Create any blog post the storefront defines but the DB doesn't have yet.

    Insert-only, same reason as `seed_categories`: the admin's Blog → Posts
    screen owns a post's title, body and everything else from the moment it
    exists — this must never revert an edit made there on the next restart.
    """
    existing_slugs = {slug for (slug,) in db.query(BlogPost.slug).all()}
    created = 0

    for item in rows:
        slug = (item.get("slug") or "").strip()
        if not slug or slug in existing_slugs:
            continue
        category = categories.get((item.get("categorySlug") or "").strip())
        row = BlogPost(
            id=str(uuid.uuid4()),
            slug=slug,
            title=item.get("title") or slug,
            excerpt=item.get("excerpt") or item.get("summary") or "",
            content=_post_html(item),
            status="published",
            category_id=category.id if category else None,
            category_name=category.name if category else item.get("category"),
            author_name=item.get("author") or "Excellent Technology BD",
            cover_image_url=item.get("cover") or item.get("image") or None,
            seo_title=item.get("title") or slug,
            seo_description=(item.get("excerpt") or item.get("summary") or "")[:500],
            published_at=_parse_date(item.get("date")) or datetime.utcnow(),
        )
        db.add(row)
        created += 1

    db.flush()
    return created


def main() -> None:
    blog = load_blog()
    db = SessionLocal()
    try:
        has_data = db.query(BlogPost).first() is not None or db.query(BlogCategory).first() is not None
        if already_seeded(db, "excellent_blog_seeded", has_data=has_data):
            print("Blog already seeded; skipping.")
            return
        categories = seed_categories(db, blog.get("categories") or [])
        created = seed_posts(db, blog.get("posts") or [], categories)
        mark_seeded(db, "excellent_blog_seeded")
        db.commit()
        print(f"Blog posts created={created}")
        print("Blog seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
