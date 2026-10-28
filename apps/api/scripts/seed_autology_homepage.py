"""Seed the storefront home page CMS with Autology's own hero and banners.

The base install ships placeholder hero slides whose images do not exist in the
Autology storefront's `public/`, so the hero renders blank until someone uploads
replacements — and it seeds them *before* this script ever runs, so the row is
never actually empty on a fresh database. This writes the shop's bundled
banners into the CMS instead, so a fresh database shows the home page the
static build showed — and the admin can then edit it from Website → Homepage.

Guarded by a `platform_settings` flag rather than "is the section empty",
because it isn't: this runs once, overwriting the base install's placeholder
regardless of what's there, then never touches the row again.

The storefront's category *icon strip* (AC, Drone, Gimbal, …) is a flat,
decorative list of product types, not a curated pin of real catalog
categories — the CMS's own category carousel model requires each entry to
reference a real `category_id`, which this list has no match for. It is left
out here and stays bundled in the storefront; seeding it as fake category
pins broke `GET /storefront/homepage` outright (a validation error, 500, for
every caller, admin editor included) rather than degrading gracefully.

Source is the same storefront export the catalog and page seeders read:

    curl http://localhost:3002/api/dev/catalog-export
      > apps/api/scripts/data/autology_catalog.json

Usage (API container):

    python scripts/seed_autology_homepage.py
"""

from __future__ import annotations

import json
from pathlib import Path

from app.database import SessionLocal
from app.models.platform_setting import PlatformSetting
from app.models.website_homepage import (
    DEFAULT_WEBSITE_HOMEPAGE_ID,
    WebsiteHomepage,
    dump_json,
    load_json,
)

DATA_PATH = Path(__file__).resolve().parent / "data" / "excellent_catalog.json"

DONE_FLAG = "autology_homepage_seeded"


def _slides(banners: list[dict], prefix: str) -> list[dict]:
    slides = []
    for i, banner in enumerate(banners, start=1):
        image = (banner.get("image") or "").strip()
        if not image:
            continue
        href = (banner.get("href") or "").strip()
        slides.append(
            {
                "id": f"{prefix}{i}",
                "image_url": image,
                # "#" is the storefront's placeholder for "no link yet".
                "href": "" if href in ("", "#") else href,
                "alt": (banner.get("alt") or "").strip(),
                "object_fit": "fill",
                "hidden": False,
            }
        )
    return slides


def load_homepage() -> dict:
    if not DATA_PATH.exists():
        raise SystemExit(
            f"Missing {DATA_PATH} — export it from the storefront first:\n"
            "  curl http://localhost:3002/api/dev/catalog-export "
            "> apps/api/scripts/data/autology_catalog.json"
        )
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return payload.get("homepage") or {}


def seed_homepage(db) -> dict[str, int]:
    """Overwrite the hero and banners with the storefront's bundled data.

    Runs once, gated by `DONE_FLAG` in `main` — see module docstring for why
    that flag, not "is the section empty", is what decides whether to write.
    """
    source = load_homepage()
    row = db.get(WebsiteHomepage, DEFAULT_WEBSITE_HOMEPAGE_ID)
    if row is None:
        raise SystemExit("Homepage row missing — run the API bootstrap first.")

    content = load_json(row.content_json, {})
    if not isinstance(content, dict):
        content = {}

    counts = {"hero": 0, "banners": 0}

    hero = _slides(source.get("hero") or [], "s")
    if hero:
        content["hero"] = {**(content.get("hero") or {}), "slides": hero}
        counts["hero"] = len(hero)

    side = _slides(source.get("side_banners") or [], "b")
    if side:
        content["banners"] = {**(content.get("banners") or {}), "slides": side}
        counts["banners"] = len(side)

    # A category carousel entry has to reference a real catalog category (see
    # module docstring) — this leaves that section alone entirely rather than
    # writing something the schema will reject.

    if any(counts.values()):
        row.content_json = dump_json(content)
    return counts


def main() -> None:
    db = SessionLocal()
    try:
        if db.get(PlatformSetting, DONE_FLAG) is not None:
            print("Homepage already seeded; skipping.")
            return

        counts = seed_homepage(db)
        db.add(
            PlatformSetting(
                key=DONE_FLAG,
                value="1",
                description="One-time Autology homepage hero/banner seed has run.",
            )
        )
        db.commit()
        print(f"Homepage seeded: hero={counts['hero']} banners={counts['banners']}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
