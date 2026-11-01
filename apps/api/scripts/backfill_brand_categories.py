"""File every product under its brand's category: Components > Motherboard > Gigabyte > product.

    python backfill_brand_categories.py            -> dry run (prints the plan, writes nothing)
    python backfill_brand_categories.py --apply
"""
import re, sys
import main  # noqa: F401
from app.database import SessionLocal
from app.models.catalog_brand import CatalogBrand
from app.models.catalog_category import CatalogCategory
from app.models.catalog_product import CatalogProduct
from app.routers.catalog_products import _apply_product_categories, _category_ids_for_product
from app.services.catalog_ai.importer_service import IMPORT_CHANNEL, brand_level_category, same_brand

APPLY = "--apply" in sys.argv
db = SessionLocal()
key = lambda t: re.sub(r"[^a-z0-9]+", "", (t or "").lower())

plan: dict = {}
skipped = {"no brand": 0, "already the brand level": 0, "no category": 0}
for p in db.query(CatalogProduct).order_by(CatalogProduct.name).all():
    brand = (db.get(CatalogBrand, p.brand_id).name if p.brand_id and db.get(CatalogBrand, p.brand_id) else (p.brand or "")).strip()
    cat = db.get(CatalogCategory, p.category_id) if p.category_id else None
    if cat is None or cat.channel != IMPORT_CHANNEL:
        skipped["no category"] += 1
        continue
    if not brand:
        skipped["no brand"] += 1
        continue
    if same_brand(cat.name, brand):
        skipped["already the brand level"] += 1
        continue
    plan.setdefault((cat.id, key(brand)), {"parent": cat, "brand": brand, "products": []})["products"].append(p)

print(f"{sum(len(v['products']) for v in plan.values())} products -> {len(plan)} brand categories  (skipped: {skipped})\n")
by_parent: dict = {}
for v in plan.values():
    by_parent.setdefault(v["parent"].name, []).append(v)
for parent, items in sorted(by_parent.items()):
    existing = sum(1 for v in items if brand_level_category(db, v["parent"].company_id, v["parent"], v["brand"], create=False) is not None)
    print(f"  {parent}:  " + ", ".join(f"{v['brand']}({len(v['products'])})" for v in sorted(items, key=lambda v: v["brand"].lower())) + (f"   [{existing} already exist]" if existing else ""))

if not APPLY:
    print("\ndry run - nothing written")
    sys.exit(0)

created = moved = 0
for v in plan.values():
    parent = v["parent"]
    had = brand_level_category(db, parent.company_id, parent, v["brand"], create=False) is not None
    child = brand_level_category(db, parent.company_id, parent, v["brand"], create=True)
    created += 0 if had else 1
    for p in v["products"]:
        old = [c for c in _category_ids_for_product(db, p) if c != child.id]
        ids = [child.id, *([parent.id] if parent.id not in old else []), *old]
        _apply_product_categories(db, p, ids)
        moved += 1
db.commit()
print(f"\nAPPLIED: {created} brand categories created, {moved} products moved")
