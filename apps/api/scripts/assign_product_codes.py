"""One-off: give every EXISTING catalog product its code (EX000001, EX000002 ...) as its SKU - the same as its serial number.

New products get theirs automatically (see CatalogProduct); this rewrites the products that were made before:

  - catalog_products.sku  = EX + serial_no (6 digits)           the serial numbers are given at startup (ensure_catalog_product_serial)
  - items.sku             = the product's code                  (items that are catalog products; other items are left alone)
  - variants' sku         = the product's code for a plain product with one variant, else EX000123-1, EX000123-2 ... (in their order)
  - inventory_stock_levels / inventory_serials sku              = the new SKU of the variant / item they belong to (state, not documents)
  - catalog_products.updated_at                                  = moved on, so every browser re-reads the products (its list is cached)

Documents that carry a SKU as written at the time (order, purchase, RMA lines, carts) are history and are NOT changed.
The old SKUs are NOT kept anywhere in the system - the JSON printed first (BACKUP_BEGIN ... BACKUP_END) is the only record: save it.

DRY=1 (default) does everything in one transaction and rolls it back; DRY=0 commits.
"""
import json
import os
import sys

from sqlalchemy import create_engine, text

DRY = os.environ.get("DRY", "1") == "1"
engine = create_engine(os.environ["DATABASE_URL"])
PREFIX, WIDTH = "EX", 6


class Stop(Exception):
    pass


def code(n: int) -> str:
    return f"{PREFIX}{int(n):0{WIDTH}d}"


try:
    with engine.begin() as c:
        scalar = lambda sql, **p: c.execute(text(sql), p).scalar()  # noqa: E731
        rows = lambda sql, **p: [dict(r._mapping) for r in c.execute(text(sql), p)]  # noqa: E731

        if scalar("select count(*) from catalog_products where serial_no is null"):
            raise Stop("some products have no serial_no yet - start the API once (ensure_catalog_product_serial) and run this again")
        products = rows("select id, item_id, sku, serial_no from catalog_products order by serial_no")
        # the codes must not already be in use by anything that is not going to be rewritten
        taken = scalar(
            r"select count(*) from (select sku from catalog_products where sku ~ '^EX[0-9]{6}(-[0-9]+)?$' union all "
            r"select sku from catalog_product_variants where sku ~ '^EX[0-9]{6}(-[0-9]+)?$' union all "
            r"select sku from items where sku ~ '^EX[0-9]{6}(-[0-9]+)?$') x"
        )
        already = scalar("select count(*) from catalog_products where sku = 'EX' || lpad(serial_no::text, 6, '0')")
        print("existing EX-codes before:", taken, "| products already on their code:", already)

        # ---- backup (what is changed)
        items_before = rows(
            "select i.id, i.sku from items i where exists (select 1 from catalog_products p where p.id = i.id or p.item_id = i.id)"
        )
        variants_before = rows("select id, product_id, sku from catalog_product_variants")
        print("BACKUP_BEGIN")
        print(json.dumps({
            "products": [{"id": p["id"], "serial_no": p["serial_no"], "sku": p["sku"]} for p in products],
            "items": items_before,
            "variants": variants_before,
        }, ensure_ascii=False))
        print("BACKUP_END")

        # ---- products
        c.execute(text("update catalog_products set sku = 'EX' || lpad(serial_no::text, 6, '0')"))
        # ---- items that are catalog products
        c.execute(text("update items i set sku = p.sku from catalog_products p where i.id = coalesce(p.item_id, p.id)"))
        # ---- variants
        c.execute(text(
            """WITH v AS (
                 SELECT v.id, p.sku AS psku,
                        COUNT(*) OVER (PARTITION BY v.product_id) AS cnt,
                        ROW_NUMBER() OVER (PARTITION BY v.product_id ORDER BY v.sort_order, v.created_at, v.id) AS rn,
                        (v.options_json IS NULL OR v.options_json IN ('', '{}', 'null', '[]')) AS plain
                 FROM catalog_product_variants v JOIN catalog_products p ON p.id = v.product_id)
               UPDATE catalog_product_variants x
                  SET sku = CASE WHEN v.cnt = 1 AND v.plain THEN v.psku ELSE v.psku || '-' || v.rn END
                 FROM v WHERE x.id = v.id"""
        ))
        # ---- tell every admin screen: the products changed. The Products list is kept in each browser and refreshed only with the
        # products whose updated_at is newer than its newest one, so without this the old SKUs / UUIDs would stay on screen for hours.
        # (A little later than now and in the old order, so the list does not shuffle.)
        c.execute(text(
            """UPDATE catalog_products p SET updated_at = now() + (r.rn || ' milliseconds')::interval
               FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY updated_at, id) AS rn FROM catalog_products) r WHERE p.id = r.id"""
        ))
        # ---- state tables that copy the SKU
        c.execute(text("update inventory_stock_levels s set sku = v.sku from catalog_product_variants v where s.variant_id = v.id"))
        c.execute(text("update inventory_serials s set sku = i.sku from items i where s.item_id = i.id"))

        # ---- verify
        bad = {
            "products_not_on_code": scalar("select count(*) from catalog_products where sku <> 'EX' || lpad(serial_no::text, 6, '0')"),
            "items_not_equal_product": scalar("select count(*) from catalog_products p join items i on i.id = coalesce(p.item_id, p.id) where i.sku <> p.sku"),
            "variants_not_prefixed": scalar("select count(*) from catalog_product_variants v join catalog_products p on p.id = v.product_id where v.sku <> p.sku and v.sku not like p.sku || '-%'"),
            "dup_variant_sku": scalar("select count(*) from (select sku from catalog_product_variants group by sku having count(*) > 1) x"),
            "stock_levels_off": scalar("select count(*) from inventory_stock_levels s join catalog_product_variants v on v.id = s.variant_id where s.sku <> v.sku"),
        }
        summary = {
            "dry_run": DRY, "products": len(products), "items_rewritten": len(items_before), "variants": len(variants_before),
            "sample": rows("select sku, serial_no from catalog_products order by serial_no limit 3"),
            "variant_sample": rows("select v.sku from catalog_product_variants v where v.sku like '%-%' order by v.sku limit 6"),
            "checks": bad,
        }
        print("SUMMARY", json.dumps(summary, ensure_ascii=False, default=str))
        if any(bad.values()):
            raise Stop("verification failed")
        if DRY:
            raise Stop("DRY RUN - rolled back")
except Stop as exc:
    print("STOPPED:", exc)
    sys.exit(0)
print("COMMITTED")
