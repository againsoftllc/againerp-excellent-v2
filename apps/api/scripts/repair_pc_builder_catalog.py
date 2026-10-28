"""Assign PC parts to the correct catalog leaf and publish builder-slot drafts.

Products seeded under parent `component` were also linked to every child category,
so the CPU builder slot listed motherboards and PSUs. This script:

1. Moves published parent-`component` products onto the matching leaf.
2. Publishes draft parts that fill empty builder slots (CPU, cooler, keyboard, …).

Usage (API container):

    python scripts/repair_pc_builder_catalog.py
"""

from __future__ import annotations

from app.database import SessionLocal
from app.models.catalog_attribute_profile import CatalogAttributeProfile  # noqa: F401
from app.models.catalog_brand import CatalogBrand  # noqa: F401
from app.models.catalog_category import CatalogCategory
from app.models.catalog_product import CatalogProduct
from app.models.ecommerce_item import EcommerceItem
from app.models.item import Item
from app.services.ecommerce.ecommerce_item_service import EcommerceItemService

_COMPONENT_LEAF_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("component-motherboard", ("motherboard", "mainboard")),
    ("component-graphics-card", ("graphics card", "geforce", "radeon", "rtx ", "gtx ", "gddr")),
    ("component-power-supply", ("power supply", "80 plus", "80+", "psu")),
    ("component-casing", ("gaming case", "atx case", "mid tower", "full tower", "mini tower")),
    ("component-ssd-hdd", ("nvme", "ssd", "hdd", "solid state")),
    ("component-ram", ("desktop ram", "ddr5", "ddr4", "memory kit")),
    ("component-cpu-cooler", ("cpu cooler", "air cooler", "aio", "liquid cooler")),
    ("component-processor", ("processor", "ryzen", "core i", "cpu ")),
]


def _leaf_category_slug(name: str, category_slug: str, children_by_parent: dict[str, list[str]]) -> str:
    children = children_by_parent.get(category_slug) or []
    if not children:
        return category_slug
    hay = f" {name.lower()} "
    for slug, hints in _COMPONENT_LEAF_HINTS:
        if slug not in children:
            continue
        if any(h in hay for h in hints):
            return slug
    return category_slug

DRAFT_SLOT_BINDS: list[tuple[str, str]] = [
    ("AMD Ryzen 7 7800X3D", "component-processor"),
    ("Intel Core i7-14700K", "component-processor"),
    ("ASUS Prime Z790-P WiFi", "component-motherboard"),
    ("MSI MAG B650 Tomahawk WiFi", "component-motherboard"),
    ("Cooler Master Hyper 212 Black", "component-cpu-cooler"),
    ("Corsair Vengeance 32GB DDR5", "component-ram"),
    ("Samsung 990 Pro 1TB NVMe", "component-ssd-hdd"),
    ("ASUS ROG Strix RTX 4070", "component-graphics-card"),
    ("Corsair RM750x 750W 80+ Gold", "component-power-supply"),
    ("NZXT H5 Flow Mid Tower Case", "component-casing"),
    ("Deepcool FC120 ARGB Case Fan (3-Pack)", "component-cpu-cooler"),
    ("LG UltraWide 34WP65C", "monitor"),
    ('Samsung 27" Odyssey G5', "monitor"),
    ("Keychron K2 Pro", "accessories-all-accessories"),
    ("Logitech G502 X Gaming Mouse", "accessories-all-accessories"),
    ("Logitech MX Master 3S", "accessories-all-accessories"),
    ("Razer DeathAdder V3", "accessories-all-accessories"),
    ("Sony WH-1000XM5", "accessories-all-accessories"),
    ("APC Back-UPS 1000VA", "ups-ips"),
]


def _cats(db) -> dict[str, CatalogCategory]:
    return {c.slug: c for c in db.query(CatalogCategory).all()}


def _set_leaf(db, svc: EcommerceItemService, ec: EcommerceItem, leaf: CatalogCategory, parent: CatalogCategory | None) -> None:
    ids = [leaf.id]
    if parent and parent.id not in ids:
        ids.append(parent.id)
    item_id = ec.item_id
    svc.replace_categories(item_id, ids, primary_category_id=leaf.id, company_id=ec.company_id)
    if ec.catalog_product_id:
        product = db.get(CatalogProduct, ec.catalog_product_id)
        if product:
            product.category_id = leaf.id
            product.category = leaf.name


def repair_published_components(db) -> int:
    cats = _cats(db)
    parent = cats.get("component")
    if not parent:
        return 0
    children_by_parent = {"component": [slug for slug in cats if slug.startswith("component-")]}
    svc = EcommerceItemService(db)
    moved = 0
    rows = (
        db.query(EcommerceItem)
        .filter(EcommerceItem.primary_category_id == parent.id)
        .all()
    )
    for ec in rows:
        item = db.get(Item, ec.item_id)
        name = item.name if item else ""
        leaf_slug = _leaf_category_slug(name, "component", children_by_parent)
        leaf = cats.get(leaf_slug)
        if not leaf or leaf.id == parent.id:
            continue
        _set_leaf(db, svc, ec, leaf, parent)
        moved += 1
        print(f"  reassigned {name} → {leaf.slug}")
    return moved


def publish_builder_drafts(db) -> int:
    cats = _cats(db)
    svc = EcommerceItemService(db)
    published = 0
    for name, slug in DRAFT_SLOT_BINDS:
        leaf = cats.get(slug)
        if not leaf:
            print(f"  skip draft {name}: missing category {slug}")
            continue
        item = db.query(Item).filter(Item.name == name).first()
        if not item:
            print(f"  skip draft {name}: not in catalog")
            continue
        ec = db.query(EcommerceItem).filter(EcommerceItem.item_id == item.id).first()
        if not ec:
            print(f"  skip draft {name}: no ecommerce row")
            continue
        parent = cats.get("component") if slug.startswith("component-") else None
        _set_leaf(db, svc, ec, leaf, parent)
        ec.publish_status = "published"
        ec.visibility = "public"
        ec.is_active = True
        if ec.catalog_product_id:
            product = db.get(CatalogProduct, ec.catalog_product_id)
            if product:
                product.status = "published"
                product.visibility = "public"
        published += 1
        print(f"  published {name} → {slug}")
    return published


def main() -> None:
    db = SessionLocal()
    try:
        print("Repair published PC Components…")
        moved = repair_published_components(db)
        print("Publish builder-slot drafts…")
        published = publish_builder_drafts(db)
        db.commit()
        print(f"Done. reassigned={moved} published={published}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
