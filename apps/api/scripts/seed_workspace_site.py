"""Seed the primary Excellent Technology BD workspace site (id=co1).

Branding here is the single source of truth the storefront reads through
``/api/v1/storefront/settings`` — it mirrors ``excellent-web/src/data/seed.ts`` (SEED_SETTINGS).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models.website_settings import DEFAULT_WEBSITE_SETTINGS_ID, WebsiteSettings  # noqa: E402
from app.models.workspace_site import DEFAULT_SITE_ID, WorkspaceSite  # noqa: E402
from app.routers.workspace_sites import _sync_website_settings  # noqa: E402


PHONE = "01913-004278"
SITE_NAME = "Excellent Technology BD"
DOMAIN = "excellenttechnology.com.bd"
LOCAL_STOREFRONT = "http://localhost:3003"


def seed_primary_site(db) -> int:
    row = db.get(WorkspaceSite, DEFAULT_SITE_ID)
    created = 0
    if not row:
        row = WorkspaceSite(id=DEFAULT_SITE_ID)
        db.add(row)
        created = 1

    row.company_id = "default"
    row.code = "EXT"
    row.name = SITE_NAME
    row.status = "active"
    row.plan = "Growth"
    row.owner = "Againsoft"
    row.primary_domain = DOMAIN
    row.domain_aliases = "www.excellenttechnology.com.bd,localhost:3003"
    row.storefront_url_local = LOCAL_STOREFRONT
    row.storefront_url_preview = f"https://{DOMAIN}"
    row.storefront_url_production = f"https://{DOMAIN}"
    row.git_repo_url = ""
    row.git_default_branch = "main"
    row.vercel_project_id = ""
    row.vercel_project_name = ""
    row.vercel_team_slug = ""
    row.tagline = "Laptop, Desktop & IT Shop in Dhaka"
    row.logo_url = ""
    row.logo_mobile_url = ""
    row.favicon_url = ""
    row.address = (
        "Shop# 315 (3rd Floor), BCS Computer City, IDB Bhaban, Agargaon, Dhaka-1207"
    )
    row.contact_phone = PHONE
    row.contact_email = f"info@{DOMAIN}"
    row.whatsapp_number = PHONE
    row.copyright_text = "© 2026 Againcart. All rights reserved."
    row.business_hours = "Saturday – Thursday, 10:00 AM – 8:00 PM"
    row.meta_title = f"{SITE_NAME} — Laptop, Desktop & IT Shop in Dhaka"
    row.meta_description = (
        f"Shop laptops, desktops, components, and gadgets online at {SITE_NAME}."
    )
    row.meta_keywords = "laptop, desktop, computer, monitor, pc builder, dhaka, bangladesh, excellent technology"
    from app.services.site_store_options import dump_site_options

    row.options_json = dump_site_options({})
    row.currency = "BDT"
    row.timezone = "Asia/Dhaka"
    row.notes = "Primary storefront site"
    row.is_primary = True

    # Ensure no other primary
    for other in db.query(WorkspaceSite).filter(WorkspaceSite.id != DEFAULT_SITE_ID).all():
        other.is_primary = False

    _sync_website_settings(db, row)
    # Prefer Againcart naming on website_settings even if row existed with AgainERP defaults
    settings = db.get(WebsiteSettings, DEFAULT_WEBSITE_SETTINGS_ID)
    if settings:
        settings.site_name = row.name
        settings.contact_phone = row.contact_phone
        settings.contact_email = row.contact_email
        settings.whatsapp_number = row.whatsapp_number
        settings.address = row.address
        settings.copyright_text = row.copyright_text
        settings.tagline = row.tagline

    db.commit()
    return created


def main() -> None:
    db = SessionLocal()
    try:
        created = seed_primary_site(db)
        print(f"ok site={DEFAULT_SITE_ID} created={created}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
