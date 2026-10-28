"""Seed the Autology offer pages and Happy Hour campaign from the storefront export.

Campaigns are definitions — title, dates, which categories or products they
cover — and the catalog supplies the products themselves. Seeding them means the
shop's offers and Happy Hour become admin-editable instead of hard-coded.

Source:

    curl http://localhost:3002/api/dev/catalog-export
      > apps/api/scripts/data/autology_catalog.json

Usage (API container):

    python scripts/seed_autology_campaigns.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import scripts.init_db  # noqa: F401 — registers every ORM model before mapping
from app.database import SessionLocal
from app.models.marketing_happy_hour import (
    MarketingHappyHour,
    MarketingHappyHourDeal,
    MarketingHappyHourSection,
)
from app.models.marketing_offer import MarketingOffer, MarketingOfferSection
from app.services.seed_once import already_seeded, mark_seeded

DATA_PATH = Path(__file__).resolve().parent / "data" / "excellent_catalog.json"

#: How far to push an already-expired campaign so it stays visible.
DEFAULT_RUN_DAYS = timedelta(days=30)


def _parse_date(value: str | None, fallback: datetime | None = None) -> datetime | None:
    if not value:
        return fallback
    text = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return fallback


def load_payload() -> dict:
    if not DATA_PATH.exists():
        raise SystemExit(
            f"Missing {DATA_PATH} — export it from the storefront first:\n"
            "  curl http://localhost:3002/api/dev/catalog-export "
            "> apps/api/scripts/data/autology_catalog.json"
        )
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def seed_offers(db, rows: list[dict]) -> int:
    """Create any offer the storefront defines but the DB doesn't have yet.

    Insert-only: this boots on every API start, and once an offer exists the
    admin's Marketing → Offers screen owns its title, dates and sections.
    """
    existing = {o.slug for o in db.query(MarketingOffer).all()}
    created = 0

    for order, item in enumerate(rows):
        slug = (item.get("slug") or "").strip()
        if not slug or slug in existing:
            continue

        now = datetime.utcnow()
        starts = _parse_date(item.get("start_date"), now)
        ends = _parse_date(item.get("end_date_iso")) or _parse_date(item.get("end_date"), now)
        # The storefront's bundled campaign dates are stale — the offer list
        # drops anything already ended. Keep the window open on the way in;
        # real dates are the admin's to set from here.
        if ends is None or ends < now:
            ends = now + DEFAULT_RUN_DAYS

        row = MarketingOffer(
            slug=slug,
            title=item.get("title") or slug,
            description=item.get("description") or "",
            image_url=item.get("image") or None,
            outlet_label=item.get("outlet_label") or "All Outlet",
            starts_at=starts,
            ends_at=ends,
            # "running" is the API's "show it regardless of the window" state,
            # matching how the storefront treated these campaigns before they
            # moved into the database.
            status="running",
            sort_order=order,
        )
        db.add(row)
        db.flush()

        for i, section in enumerate(item.get("sections") or []):
            db.add(
                MarketingOfferSection(
                    offer_id=row.id,
                    key=section.get("key") or f"s{i + 1}",
                    label=section.get("label") or "",
                    category_slug=section.get("category_slug") or section.get("key") or "",
                    sort_order=i,
                )
            )
        created += 1

    db.flush()
    return created


def seed_happy_hour(db, campaign: dict) -> int:
    """Create the Happy Hour campaign if the DB doesn't have it yet.

    Insert-only, same reason as `seed_offers`: once it exists, the admin's
    Marketing → Happy Hour screen owns its dates, sections and deals. Returns
    the number of deals seeded (0 if the campaign already existed).
    """
    slug = (campaign.get("slug") or "").strip()
    if not slug or db.query(MarketingHappyHour).filter(MarketingHappyHour.slug == slug).first():
        return 0

    now = datetime.utcnow()
    ends = _parse_date(campaign.get("endDateISO"), now)
    row = MarketingHappyHour(
        slug=slug,
        title=campaign.get("title") or slug,
        subtitle=campaign.get("subtitle"),
        description=campaign.get("description") or "",
        outlet_label=campaign.get("outletLabel") or "Online Only",
        starts_at=_parse_date(campaign.get("startDateISO"), now),
        ends_at=ends if ends and ends >= now else now + DEFAULT_RUN_DAYS,
        daily_start_hour=int(campaign.get("dailyStartHour") or 22),
        daily_end_hour=int(campaign.get("dailyEndHour") or 24),
        status="running" if campaign.get("status", True) else "draft",
        terms_json=json.dumps(campaign.get("terms") or [], ensure_ascii=False),
    )
    db.add(row)
    db.flush()

    deals = 0
    for i, section in enumerate(campaign.get("sections") or []):
        section_row = MarketingHappyHourSection(
            campaign_id=row.id,
            key=section.get("key") or f"s{i + 1}",
            label=section.get("label") or "",
            sort_order=i,
        )
        db.add(section_row)
        db.flush()
        for j, deal in enumerate(section.get("deals") or []):
            product_slug = (deal.get("slug") or "").strip()
            if not product_slug:
                continue
            db.add(
                MarketingHappyHourDeal(
                    section_id=section_row.id,
                    product_slug=product_slug,
                    offer_price=float(deal.get("offerPrice") or 0),
                    note=deal.get("note"),
                    sort_order=j,
                )
            )
            deals += 1
    return deals


def main() -> None:
    payload = load_payload()
    db = SessionLocal()
    try:
        has_data = db.query(MarketingOffer).first() is not None or db.query(MarketingHappyHour).first() is not None
        if already_seeded(db, "excellent_campaigns_seeded", has_data=has_data):
            print("Campaigns already seeded; skipping.")
            return
        created = seed_offers(db, payload.get("offers") or [])
        deals = seed_happy_hour(db, payload.get("happy_hour") or {})
        mark_seeded(db, "excellent_campaigns_seeded")
        db.commit()
        print(f"Offers created={created} | Happy Hour deals={deals}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
