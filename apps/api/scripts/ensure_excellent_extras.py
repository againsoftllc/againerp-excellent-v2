"""Columns and seeds the Excellent storefront layer needs on top of the Moharaz schema.

Everything here is additive and idempotent (ADD COLUMN IF NOT EXISTS / insert-if-missing),
so it is safe to run on every boot.
"""
from __future__ import annotations

from sqlalchemy import text

from app.database import engine


def ensure_catalog_product_special_columns() -> None:
    """Nightly window + Happy Hour/Offer campaign link on OpenCart-style specials."""
    statements = [
        "ALTER TABLE catalog_product_specials ADD COLUMN IF NOT EXISTS daily_start_hour INTEGER",
        "ALTER TABLE catalog_product_specials ADD COLUMN IF NOT EXISTS daily_end_hour INTEGER",
        "ALTER TABLE catalog_product_specials ADD COLUMN IF NOT EXISTS happy_hour_campaign_id VARCHAR(36) REFERENCES marketing_happy_hours(id) ON DELETE CASCADE",
        "CREATE INDEX IF NOT EXISTS ix_catalog_product_specials_happy_hour_campaign_id ON catalog_product_specials (happy_hour_campaign_id)",
        "ALTER TABLE catalog_product_specials ADD COLUMN IF NOT EXISTS offer_campaign_id VARCHAR(36) REFERENCES marketing_offers(id) ON DELETE CASCADE",
        "CREATE INDEX IF NOT EXISTS ix_catalog_product_specials_offer_campaign_id ON catalog_product_specials (offer_campaign_id)",
        "ALTER TABLE catalog_product_specials ADD COLUMN IF NOT EXISTS quantity INTEGER",
        "ALTER TABLE catalog_product_specials ADD COLUMN IF NOT EXISTS quantity_sold INTEGER NOT NULL DEFAULT 0",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def ensure_catalog_stock_status_columns() -> None:
    """"Call for Price" per-status default contact number, plus the "call_for_price" status."""
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE catalog_stock_statuses ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(30)")
        )
        exists = conn.execute(
            text("SELECT 1 FROM catalog_stock_statuses WHERE code = 'call_for_price'")
        ).first()
        if not exists:
            conn.execute(
                text(
                    "INSERT INTO catalog_stock_statuses "
                    "(id, company_id, code, label, sort_order, is_active, is_system, "
                    "counts_as_in_stock, sellable, tracks_quantity, needs_end_date, "
                    "badge_label, badge_color, show_in_filter) "
                    "VALUES (gen_random_uuid()::text, 'default', 'call_for_price', 'Call for Price', 50, "
                    "true, true, false, false, false, false, 'Call for Price', '#6c757d', true)"
                )
            )
