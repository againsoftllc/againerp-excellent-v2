"""Put the category page's filters (and each filter's options) in the SOURCE shop's own order - Star Tech's.

    python scripts/apply_filter_order.py                       # dry run, every profile below (rolled back)
    python scripts/apply_filter_order.py "Laptop Specification"
    python scripts/apply_filter_order.py --apply
    python scripts/apply_filter_order.py --apply --keep        # leave filter orders that are already set (default: Star Tech's order wins)

Only the order changes: no value, option or attribute is added or removed, and the product page keeps the specification order.
"""
import sys
import main  # noqa: F401
from app.database import SessionLocal
from app.models.catalog_attribute_profile import CatalogAttributeProfile
from app.services.catalog_ai import spec_profile_service as sp
from app.services.catalog_ai.scraper import fetch_page, fetch_trail_filters
from scripts.startech_shapes import S, SHAPES

REFERENCES = {**SHAPES, "Laptop Specification": [f"{S}/acer-nitro-5-pro-an5p16-74g2-core-i7-laptop"]}
APPLY = "--apply" in sys.argv
FORCE = "--keep" not in sys.argv
only = [a for a in sys.argv[1:] if not a.startswith("--")]
db = SessionLocal()
try:
    for name, urls in REFERENCES.items():
        if only and name not in only:
            continue
        prof = db.query(CatalogAttributeProfile).filter(CatalogAttributeProfile.name == name).first()
        if prof is None:
            print(f"- {name}: no such profile here, skipped")
            continue
        lists = []
        for u in urls:
            pg = fetch_page(u)
            lk = pg.structured.get("breadcrumb_links") or []
            lists.append(fetch_trail_filters([l["url"] for l in lk[1:-1]][:4]))
        from app.services.catalog_ai.scraper import merge_filters

        filters = merge_filters(*lists)
        n = sp.apply_source_filter_order(db, prof, filters, force=FORCE, reorder_options=True)
        print(f"- {name}: {n} of {len(filters)} source filters placed  ({', '.join(f['title'] for f in filters)})")
    if APPLY:
        db.commit()
        print("\nAPPLIED")
    else:
        db.rollback()
        print("\ndry run - nothing written")
finally:
    db.close()
