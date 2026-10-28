"""Drop the base-install demo catalog so the shop only carries Autology stock.

`scripts/init_db.py` seeds a demo catalog — products (SKU-*, erp-*), categories,
brands, blog posts — before any Autology script runs. Those rows are not
Autology's; they clutter the admin grids, and worse, some of them happen to
reuse the same slug or page id Autology's own seeders use ("accessories",
"about-us", …), so the insert-only seeders that run after this one find a row
already there and — correctly, by their own rule of never overwriting an
existing row — leave the demo content in place instead of creating Autology's.
This must run, and finish, before any `seed_autology_*` script does.

Catalog products are identified by their `ATL-` SKU prefix — every one the
catalog seeder writes carries it, so only true demo stock is removed.
Categories, brands and blog posts/categories are wiped outright rather than
matched by slug: this runs once, before Autology's seeders have created
anything of their own, so there is nothing legitimate to preserve yet, and a
demo category sharing Autology's own slug ("accessories") can't be told apart
from one that doesn't. `seed_autology_catalog.py` / `seed_autology_blog.py`
recreate the real set immediately after this, from a clean slate.

This runs once and records a `platform_settings` flag — every boot after the
first is a no-op, otherwise a restart after someone had added a real category,
brand, product or blog post would delete it.

Usage (API container):

    python scripts/purge_demo_data.py
"""

from __future__ import annotations

from sqlalchemy import text

import scripts.init_db  # noqa: F401 — registers every ORM model before mapping
from app.database import SessionLocal
from app.models.blog_category import BlogCategory
from app.models.blog_post import BlogPost
from app.models.catalog_brand import CatalogBrand
from app.models.catalog_category import CatalogCategory
from app.models.catalog_product import CatalogProduct
from app.models.ecommerce_item import EcommerceItem
from app.models.ecommerce_item_category import EcommerceItemCategory
from app.models.platform_setting import PlatformSetting

SKU_PREFIX = "EXT-"

#: Marks that this one-time purge has already run, so a later boot never
#: repeats it — the "not ATL-*" match below has no way to tell an admin-created
#: product apart from base-install demo stock, so running it a second time
#: would delete anything an admin has since added through the Catalog UI.
DONE_FLAG = "autology_demo_data_purged"

# Child rows to clear before their parent, innermost first.
PRODUCT_CHILD_TABLES = (
    "blog_post_products",
    "catalog_product_attribute_values",
    "catalog_product_digital_files",
    "catalog_product_media",
    "catalog_product_specials",
    "catalog_product_variants",
    "inventory_stock_levels",
)

ORDER_CHILD_TABLES = (
    "commerce_order_addresses",
    "commerce_order_events",
    "commerce_order_items",
    "commerce_order_shipments",
    "commerce_order_refunds",
    "commerce_order_returns",
)


def _scalar(db, sql: str, **params) -> int:
    return int(db.execute(text(sql), params).scalar() or 0)


def _exec(db, sql: str, **params) -> int:
    return int(db.execute(text(sql), params).rowcount or 0)


def _table_exists(db, name: str) -> bool:
    return bool(
        db.execute(
            text("select to_regclass(:name)"), {"name": f"public.{name}"}
        ).scalar()
    )


def purge(db) -> dict[str, int]:
    removed: dict[str, int] = {}

    demo_products = (
        "select id from catalog_products where sku is null or sku not like :prefix"
    )
    count = _scalar(db, f"select count(*) from ({demo_products}) t", prefix=f"{SKU_PREFIX}%")
    if not count:
        print("No demo catalog rows found.")
        return removed
    print(f"Demo catalog products to remove: {count}")

    # Orders that carry a demo line — remove the whole order, not just the line,
    # so no order is left with a missing product or a wrong total. Read the ids
    # up front: deleting `commerce_order_items` first would empty the lookup.
    order_ids = [
        row[0]
        for row in db.execute(
            text(
                f"""select distinct i.order_id
                    from commerce_order_items i
                    where i.product_id in ({demo_products})"""
            ),
            {"prefix": f"{SKU_PREFIX}%"},
        ).all()
    ]
    if order_ids:
        for table in ORDER_CHILD_TABLES:
            if not _table_exists(db, table):
                continue
            n = _exec(
                db,
                f"delete from {table} where order_id = any(:ids)",
                ids=order_ids,
            )
            if n:
                removed[table] = n
        n = _exec(db, "delete from commerce_orders where id = any(:ids)", ids=order_ids)
        if n:
            removed["commerce_orders"] = n

    # Sales orders line up against `items`, not `catalog_products`, so they hold
    # no foreign key into the rows being removed here and are left alone.

    # Self-referencing related-product links need both sides cleared.
    n = _exec(
        db,
        f"""delete from catalog_product_related
            where product_id in ({demo_products})
               or related_id in ({demo_products})""",
        prefix=f"{SKU_PREFIX}%",
    )
    if n:
        removed["catalog_product_related"] = n

    for table in PRODUCT_CHILD_TABLES:
        if not _table_exists(db, table):
            continue
        n = _exec(
            db,
            f"delete from {table} where product_id in ({demo_products})",
            prefix=f"{SKU_PREFIX}%",
        )
        if n:
            removed[table] = n

    if _table_exists(db, "ecommerce_item_categories"):
        n = _exec(
            db,
            f"""delete from ecommerce_item_categories where item_id in (
                    select id from ecommerce_items
                    where catalog_product_id in ({demo_products})
                )""",
            prefix=f"{SKU_PREFIX}%",
        )
        if n:
            removed["ecommerce_item_categories"] = n

    n = _exec(
        db,
        f"delete from ecommerce_items where catalog_product_id in ({demo_products})",
        prefix=f"{SKU_PREFIX}%",
    )
    if n:
        removed["ecommerce_items"] = n

    n = _exec(
        db,
        "delete from catalog_products where sku is null or sku not like :prefix",
        prefix=f"{SKU_PREFIX}%",
    )
    removed["catalog_products"] = n

    return removed


def purge_categories(db, keep: set[str]) -> int:
    """Drop catalog categories not in ``keep``.

    Called with an empty ``keep`` (wipe everything) — see module docstring for
    why: a demo category that happens to share Autology's own slug ("accessories")
    is, from here, indistinguishable from one that doesn't, and this runs
    before Autology has created anything of its own to preserve.
    """
    ids = [
        row.id
        for row in db.query(CatalogCategory).filter(CatalogCategory.channel == "catalog").all()
        if row.slug not in keep
    ]
    if not ids:
        return 0

    db.query(CatalogCategory).filter(CatalogCategory.parent_id.in_(ids)).update(
        {CatalogCategory.parent_id: None}, synchronize_session=False
    )
    db.query(EcommerceItemCategory).filter(EcommerceItemCategory.category_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(EcommerceItem).filter(EcommerceItem.primary_category_id.in_(ids)).update(
        {EcommerceItem.primary_category_id: None}, synchronize_session=False
    )
    db.query(CatalogProduct).filter(CatalogProduct.category_id.in_(ids)).update(
        {CatalogProduct.category_id: None}, synchronize_session=False
    )
    db.query(CatalogCategory).filter(CatalogCategory.id.in_(ids)).delete(synchronize_session=False)
    return len(ids)


def purge_brands(db, keep: set[str]) -> int:
    """Drop catalog brands not in ``keep``, moving their products onto the kept
    brand of the same name. Called with an empty ``keep`` — see `purge_categories`."""
    keep_rows = [row for row in db.query(CatalogBrand).all() if row.slug in keep]
    by_name: dict[str, CatalogBrand] = {}
    for row in keep_rows:
        by_name.setdefault(row.name.lower(), row)

    leftovers = [row for row in db.query(CatalogBrand).all() if row.slug not in keep]
    if not leftovers:
        return 0

    leftover_ids = [row.id for row in leftovers]
    for row in leftovers:
        target = by_name.get(row.name.lower())
        if target is not None and target.id != row.id:
            db.query(CatalogProduct).filter(CatalogProduct.brand_id == row.id).update(
                {CatalogProduct.brand_id: target.id, CatalogProduct.brand: target.name},
                synchronize_session=False,
            )
            db.query(EcommerceItem).filter(EcommerceItem.brand_id == row.id).update(
                {EcommerceItem.brand_id: target.id}, synchronize_session=False
            )
        else:
            db.query(CatalogProduct).filter(CatalogProduct.brand_id == row.id).update(
                {CatalogProduct.brand_id: None}, synchronize_session=False
            )
            db.query(EcommerceItem).filter(EcommerceItem.brand_id == row.id).update(
                {EcommerceItem.brand_id: None}, synchronize_session=False
            )

    db.query(CatalogBrand).filter(CatalogBrand.id.in_(leftover_ids)).delete(
        synchronize_session=False
    )
    return len(leftover_ids)


def purge_blog(db, keep_posts: set[str], keep_categories: set[str]) -> tuple[int, int]:
    """Drop blog posts and categories not in the keep sets. Called with empty
    sets — see `purge_categories`."""
    post_rows = [row for row in db.query(BlogPost).all() if row.slug not in keep_posts]
    for row in post_rows:
        db.delete(row)

    cat_ids = [
        row.id for row in db.query(BlogCategory).all() if row.slug not in keep_categories
    ]
    if cat_ids:
        db.query(BlogPost).filter(BlogPost.category_id.in_(cat_ids)).update(
            {BlogPost.category_id: None}, synchronize_session=False
        )
        db.query(BlogCategory).filter(BlogCategory.id.in_(cat_ids)).delete(
            synchronize_session=False
        )
    return len(post_rows), len(cat_ids)


def main() -> None:
    db = SessionLocal()
    try:
        if db.get(PlatformSetting, DONE_FLAG) is not None:
            print("Demo data already purged; skipping.")
            return

        removed = purge(db)

        # Wipe every pre-existing category, brand and blog row rather than
        # keeping the ones that happen to share Autology's own slugs — this
        # runs once, before Autology's seeders have created anything of their
        # own, so there is nothing legitimate to preserve yet, and a demo row
        # sharing a slug ("accessories") can't be told apart from one that
        # doesn't. `seed_autology_catalog.py` / `seed_autology_blog.py` recreate
        # the real set immediately after this, from a clean slate.
        n = purge_categories(db, set())
        if n:
            removed["catalog_categories"] = n
        n = purge_brands(db, set())
        if n:
            removed["catalog_brands"] = n
        posts_removed, cats_removed = purge_blog(db, set(), set())
        if posts_removed:
            removed["blog_posts"] = posts_removed
        if cats_removed:
            removed["blog_categories"] = cats_removed

        db.add(
            PlatformSetting(
                key=DONE_FLAG,
                value="1",
                description="One-time Autology demo-catalog purge has run.",
            )
        )
        db.commit()
        if removed:
            for table, n in removed.items():
                print(f"  {table}: {n}")
        print("Demo data purge complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
