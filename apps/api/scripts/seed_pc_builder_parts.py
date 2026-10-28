"""Seed real, discrete PC-component products with compatibility attributes.

Smart PC Builder Phase 1 needs something to actually check: today the
component-* categories exist only as slugs the Configurator's slot config
expects, and no catalog product carries a socket/ram_type/tdp/wattage/
socket_support value. This script creates the missing child categories, a
small attribute set for them, and a handful of real CPU/Motherboard/RAM/
Cooler/PSU/Case/GPU/SSD products — including a couple of deliberately
mismatched ones (AM4 board, high-TDP CPU, sub-550W PSU) so the rule engine
has both a pass and a fail to demonstrate.

Idempotent — safe to re-run; matches products/categories by slug and updates
in place rather than duplicating.

Usage (API container):
    python scripts/seed_pc_builder_parts.py
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.catalog_attribute import CatalogAttribute
from app.models.catalog_attribute_group import CatalogAttributeGroup
from app.models.catalog_attribute_profile import CatalogAttributeProfile
from app.models.catalog_brand import CatalogBrand
from app.models.catalog_category import CatalogCategory
from app.models.catalog_product import CatalogProduct
from app.models.catalog_product_attribute_value import CatalogProductAttributeValue
from app.services.ecommerce.ecommerce_item_service import EcommerceItemService
from app.services.items.catalog_item_bridge import ensure_item_for_catalog_product

PLACEHOLDER_IMAGE = "/images/products/placeholder.svg"

# slug, name, sort_order
CHILD_CATEGORIES: list[tuple[str, str, int]] = [
    ("component-processor", "Processor", 1),
    ("component-motherboard", "Motherboard", 2),
    ("component-ram", "Desktop RAM", 3),
    ("component-cpu-cooler", "CPU Cooler", 4),
    ("component-graphics-card", "Graphics Card", 5),
    ("component-power-supply", "Power Supply", 6),
    ("component-casing", "Casing", 7),
    ("component-ssd-hdd", "SSD / HDD", 8),
]

# code, name, unit
ATTRIBUTES: list[tuple[str, str, Optional[str]]] = [
    ("socket", "Socket", None),
    ("ram_type", "Memory Type", None),
    ("tdp", "TDP", "W"),
    ("wattage", "Wattage", "W"),
    ("socket_support", "Socket Support", None),
    ("chipset", "Chipset", None),
    ("generation", "Generation", None),
]

# name, brand, price, compare_at_price, category_slug, attrs
PRODUCTS: list[tuple[str, str, str, Optional[str], str, dict[str, str]]] = [
    # CPUs — one AM5 pair that fits the AM5 board, one AM4 that does not,
    # one LGA1700 pair, and a high-TDP part to trip the >125W warning.
    ("AMD Ryzen 5 7600", "AMD", "22500", None, "component-processor", {"socket": "AM5", "tdp": "65", "generation": "Ryzen 7000"}),
    ("AMD Ryzen 9 7950X", "AMD", "48500", "52000", "component-processor", {"socket": "AM5", "tdp": "170", "generation": "Ryzen 7000"}),
    ("Intel Core i5-13400", "Intel", "21000", None, "component-processor", {"socket": "LGA1700", "tdp": "65", "generation": "13th Gen"}),
    ("Intel Core i7-14700K", "Intel", "42000", "45000", "component-processor", {"socket": "LGA1700", "tdp": "125", "generation": "14th Gen"}),
    # Motherboards — AM5 + LGA1700 boards that pair correctly above, and one
    # AM4 board so an AM5 CPU pick demonstrates a real socket mismatch. Chipset
    # values here are looked up in Chipset Lookup for generation/BIOS checks.
    ("MSI MAG B650 Tomahawk WiFi", "MSI", "26500", None, "component-motherboard", {"socket": "AM5", "ram_type": "DDR5", "chipset": "B650"}),
    ("ASUS Prime Z790-P WiFi", "ASUS", "24500", None, "component-motherboard", {"socket": "LGA1700", "ram_type": "DDR5", "chipset": "Z790"}),
    ("Gigabyte A520M K Motherboard", "Gigabyte", "8200", None, "component-motherboard", {"socket": "AM4", "ram_type": "DDR4", "chipset": "A520"}),
    # RAM
    ("Corsair Vengeance 32GB (2x16GB) DDR5 6000", "Corsair", "12900", None, "component-ram", {"ram_type": "DDR5"}),
    ("Kingston Fury Beast 16GB (2x8GB) DDR4 3200", "Kingston", "5600", None, "component-ram", {"ram_type": "DDR4"}),
    # CPU coolers — both list AM5/AM4/LGA1700 so either CPU pairing above works.
    ("Cooler Master Hyper 212 Black", "Cooler Master", "3600", None, "component-cpu-cooler", {"socket_support": "AM4,AM5,LGA1700,LGA1200"}),
    ("DeepCool AK400 Air Cooler", "DeepCool", "3900", None, "component-cpu-cooler", {"socket_support": "AM4,AM5,LGA1700"}),
    # PSUs — one comfortably sized, one under 550W to trip the wattage warning.
    ("Corsair RM750x 750W 80+ Gold", "Corsair", "12500", None, "component-power-supply", {"wattage": "750"}),
    ("Antec NeoECO 450W 80+ Bronze", "Antec", "4200", None, "component-power-supply", {"wattage": "450"}),
    # Not gated by any Phase-1 rule yet — present so the slot isn't empty.
    ("NZXT H5 Flow Mid Tower Case", "NZXT", "9500", None, "component-casing", {}),
    ("ASUS Dual RTX 4070 OC 12GB", "ASUS", "68000", "72000", "component-graphics-card", {}),
    ("Samsung 990 Pro 1TB NVMe", "Samsung", "9800", None, "component-ssd-hdd", {}),
]


def ensure_categories(db: Session) -> dict[str, CatalogCategory]:
    parent = db.query(CatalogCategory).filter(CatalogCategory.slug == "component").first()
    if not parent:
        raise RuntimeError("Parent category 'component' not found — cannot anchor PC-builder leaves")

    by_slug: dict[str, CatalogCategory] = {parent.slug: parent}
    for slug, name, sort_order in CHILD_CATEGORIES:
        row = db.query(CatalogCategory).filter(CatalogCategory.slug == slug).first()
        if row is None:
            row = CatalogCategory(
                id=str(uuid.uuid4()),
                parent_id=parent.id,
                path=f"{parent.path.rstrip('/')}/{slug}",
                depth=(parent.depth or 0) + 1,
                name=name,
                slug=slug,
                sort_order=sort_order,
                is_active=True,
            )
            db.add(row)
            db.flush()
            print(f"  created category {slug}")
        else:
            changed = False
            if row.parent_id != parent.id:
                row.parent_id = parent.id
                changed = True
            if not row.is_active:
                row.is_active = True
                changed = True
            if changed:
                print(f"  fixed category {slug}")
        by_slug[slug] = row
    return by_slug


def ensure_attribute_profile(db: Session) -> CatalogAttributeProfile:
    profile = (
        db.query(CatalogAttributeProfile)
        .filter(CatalogAttributeProfile.code == "pc_builder_specs")
        .first()
    )
    if profile is None:
        profile = CatalogAttributeProfile(
            id=str(uuid.uuid4()),
            name="PC Builder Specs",
            code="pc_builder_specs",
            description="Compatibility fields the Smart PC Builder rule engine reads (socket, RAM type, TDP, wattage).",
            is_active=True,
        )
        db.add(profile)
        db.flush()
        print("  created attribute profile pc_builder_specs")
    return profile


def ensure_attribute_group(db: Session, profile: CatalogAttributeProfile) -> CatalogAttributeGroup:
    group = (
        db.query(CatalogAttributeGroup)
        .filter(CatalogAttributeGroup.code == "pc_builder")
        .first()
    )
    if group is None:
        group = CatalogAttributeGroup(
            id=str(uuid.uuid4()),
            profile_id=profile.id,
            name="PC Builder Compatibility",
            code="pc_builder",
            is_active=True,
        )
        db.add(group)
        db.flush()
        print("  created attribute group pc_builder")
    return group


def ensure_attributes(db: Session, group: CatalogAttributeGroup) -> dict[str, CatalogAttribute]:
    by_code: dict[str, CatalogAttribute] = {}
    for i, (code, name, unit) in enumerate(ATTRIBUTES):
        row = db.query(CatalogAttribute).filter(CatalogAttribute.code == code, CatalogAttribute.group_id == group.id).first()
        if row is None:
            row = CatalogAttribute(
                id=str(uuid.uuid4()),
                group_id=group.id,
                name=name,
                code=code,
                field_type="text",
                sort_order=i,
                is_filterable=False,
                is_comparable=True,
                is_visible=True,
                is_active=True,
                storefront_filter_visible=False,
                unit=unit,
            )
            db.add(row)
            db.flush()
            print(f"  created attribute {code}")
        by_code[code] = row
    return by_code


def _brand(db: Session, name: str, cache: dict[str, CatalogBrand]) -> CatalogBrand:
    key = name.lower()
    if key in cache:
        return cache[key]
    slug = name.lower().replace(" ", "-")
    row = db.query(CatalogBrand).filter((CatalogBrand.slug == slug) | (CatalogBrand.name.ilike(name))).first()
    if row is None:
        row = CatalogBrand(id=str(uuid.uuid4()), name=name, slug=slug, is_active=True)
        db.add(row)
        db.flush()
    cache[key] = row
    return row


def _set_attrs(db: Session, product_id: str, attrs: dict[str, str], attr_by_code: dict[str, CatalogAttribute]) -> None:
    for i, (code, value) in enumerate(attrs.items()):
        attr = attr_by_code.get(code)
        if not attr or not value:
            continue
        row = (
            db.query(CatalogProductAttributeValue)
            .filter(
                CatalogProductAttributeValue.product_id == product_id,
                CatalogProductAttributeValue.attribute_id == attr.id,
            )
            .first()
        )
        if row is None:
            db.add(
                CatalogProductAttributeValue(
                    id=str(uuid.uuid4()),
                    product_id=product_id,
                    attribute_id=attr.id,
                    value=value,
                    sort_order=i,
                )
            )
        else:
            row.value = value


def seed_products(
    db: Session,
    categories: dict[str, CatalogCategory],
    attribute_profile: CatalogAttributeProfile,
    attr_by_code: dict[str, CatalogAttribute],
) -> tuple[int, int]:
    brands: dict[str, CatalogBrand] = {}
    svc = EcommerceItemService(db)
    created = updated = 0

    for name, brand_name, price, compare, cat_slug, attrs in PRODUCTS:
        cat = categories.get(cat_slug)
        if not cat:
            print(f"  skip {name}: missing category {cat_slug}")
            continue

        slug = name.lower().replace(" ", "-").replace("(", "").replace(")", "").replace("+", "plus").replace("/", "-")
        brand = _brand(db, brand_name, brands)
        product = db.query(CatalogProduct).filter(CatalogProduct.slug == slug).first()
        is_new = product is None

        if is_new:
            product = CatalogProduct(id=str(uuid.uuid4()), slug=slug)
            product.sku = f"PCB-{brand_name[:4].upper()}-{product.id[:6].upper()}"
            db.add(product)
            created += 1
        else:
            updated += 1

        product.name = name
        product.price = Decimal(price)
        product.compare_at_price = Decimal(compare) if compare else None
        product.stock = 20
        product.track_quantity = True
        product.stock_status = "in_stock"
        product.status = "active"
        product.visibility = "public"
        product.brand = brand.name
        product.brand_id = brand.id
        product.category = cat.name
        product.category_id = cat.id
        product.attribute_profile_id = attribute_profile.id
        product.thumbnail = product.thumbnail or PLACEHOLDER_IMAGE
        product.short_description = product.short_description or f"{name} — in stock."
        product.description = product.description or f"<h2>{name}</h2><p>{name} from {brand.name}.</p>"
        db.flush()

        ensure_item_for_catalog_product(db, product)
        ec = svc.ensure_draft_for_catalog_product(product)
        ec.thumbnail_url = product.thumbnail
        ec.primary_category_id = cat.id
        ec.brand_id = brand.id
        ec.selling_price = product.price
        ec.compare_at_price = product.compare_at_price
        ec.short_description = product.short_description
        ec.full_description = product.description
        ec.publish_status = "published"
        ec.visibility = "public"
        ec.is_active = True

        _set_attrs(db, product.id, attrs, attr_by_code)

    return created, updated


def main() -> None:
    db = SessionLocal()
    try:
        print("Ensuring PC-builder leaf categories…")
        categories = ensure_categories(db)
        print("Ensuring PC-builder attribute profile/group/fields…")
        profile = ensure_attribute_profile(db)
        group = ensure_attribute_group(db, profile)
        attr_by_code = ensure_attributes(db, group)
        print("Seeding PC-component products…")
        created, updated = seed_products(db, categories, profile, attr_by_code)
        db.commit()
        print(f"Done. created={created} updated={updated}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
