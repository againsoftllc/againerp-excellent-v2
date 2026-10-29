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


def ensure_excellent_columns() -> None:
    """Columns the Excellent storefront layer reads/writes that the Moharaz schema never had."""
    statements = [
        "ALTER TABLE catalog_product_variants ADD COLUMN IF NOT EXISTS gallery_json TEXT",
        "ALTER TABLE storefront_customer_identities ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE storefront_customer_identities ADD COLUMN IF NOT EXISTS failed_password_attempts INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE catalog_product_attribute_values ADD COLUMN IF NOT EXISTS display_value TEXT",
        "ALTER TABLE catalog_products ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(30)",
        "ALTER TABLE catalog_products ADD COLUMN IF NOT EXISTS pre_order_ends_at TIMESTAMP",
        "ALTER TABLE catalog_products ADD COLUMN IF NOT EXISTS sale_ends_at TIMESTAMP",
        "ALTER TABLE catalog_products ADD COLUMN IF NOT EXISTS seo_keyphrase VARCHAR(255)",
        "ALTER TABLE commerce_order_items ADD COLUMN IF NOT EXISTS attributes_json TEXT",
        "ALTER TABLE marketing_coupons ADD COLUMN IF NOT EXISTS rules_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE marketing_happy_hour_deals ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE marketing_happy_hour_deals ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE marketing_happy_hour_deals ADD COLUMN IF NOT EXISTS quantity INTEGER",
        "ALTER TABLE marketing_offers ADD COLUMN IF NOT EXISTS custom_link VARCHAR(500)",
        "ALTER TABLE marketing_offers ADD COLUMN IF NOT EXISTS daily_end_hour INTEGER",
        "ALTER TABLE marketing_offers ADD COLUMN IF NOT EXISTS daily_start_hour INTEGER",
        "ALTER TABLE marketing_offers ADD COLUMN IF NOT EXISTS subtitle VARCHAR(255)",
        "ALTER TABLE marketing_offers ADD COLUMN IF NOT EXISTS terms_json TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE storefront_customer_cases ADD COLUMN IF NOT EXISTS customer_seen_at TIMESTAMP",
        "ALTER TABLE website_chat_messages ADD COLUMN IF NOT EXISTS payload_json TEXT",
        "ALTER TABLE website_chat_messages ADD COLUMN IF NOT EXISTS reaction VARCHAR(16)",
        "ALTER TABLE website_settings ADD COLUMN IF NOT EXISTS more_to_love_count INTEGER NOT NULL DEFAULT 6",
        "ALTER TABLE website_wishlists ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'wishlist'",
        "CREATE INDEX IF NOT EXISTS ix_website_wishlists_kind ON website_wishlists (kind)",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def ensure_pickup_point_columns() -> None:
    """Store Pickup branch on commerce + sales orders, backfilled from the order notes of older orders."""
    import re

    with engine.begin() as conn:
        for table in ("commerce_orders", "sales_orders"):
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS pickup_point VARCHAR(160)"))

    from app.database import SessionLocal
    from app.services.ecommerce.checkout_shipping_availability import pickup_point_label

    pattern = re.compile(r"Pickup point:\s*([^\n·]+)")
    db = SessionLocal()
    try:
        for table in ("commerce_orders", "sales_orders"):
            rows = db.execute(
                text(f"SELECT id, notes FROM {table} WHERE pickup_point IS NULL AND notes LIKE '%Pickup point:%'")
            ).all()
            for row_id, notes in rows:
                match = pattern.search(notes or "")
                label = pickup_point_label(db, match.group(1).strip()) if match else None
                if label:
                    db.execute(text(f"UPDATE {table} SET pickup_point = :p WHERE id = :i"), {"p": label, "i": row_id})
        db.commit()
    finally:
        db.close()
