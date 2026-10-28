#!/usr/bin/env python3
"""Split the single "PC Builder Specs" attribute profile into one profile per
PC component (Processor, Motherboard, Memory, Graphics Card, Power Supply,
Casing, CPU Cooler, Storage, Monitor).

Why: a product has ONE attribute profile and its form shows every group of that
profile, so a CPU used to show RAM, casing and PSU fields too. After the split a
CPU product picks "Processor" and sees only CPU fields.

What it does (all idempotent — safe to re-run):
  1. Moves each builder group (cpu, motherboard, memory, ...) under its own
     profile. Attributes keep their ids, so values already entered on products
     are untouched. "Casing" and "Monitor" already exist as profiles; the
     builder group is added to them instead of creating duplicates.
  2. Points products that sit in the builder's catalog categories at the
     matching profile (only products with no profile or on the old one —
     a product already on another profile is left alone).
  3. Scopes each profile to those catalog categories (additive).
  4. Removes the old "PC Builder Specs" profile once it is empty.

Run:  python scripts/split_pc_builder_profiles.py            # dry run, prints the plan
      python scripts/split_pc_builder_profiles.py --apply    # does it
"""

from __future__ import annotations

import sys
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.models.catalog_attribute import CatalogAttribute  # noqa: E402
from app.models.catalog_attribute_group import CatalogAttributeGroup  # noqa: E402
from app.models.catalog_attribute_profile import CatalogAttributeProfile  # noqa: E402
from app.models.catalog_attribute_profile_category import CatalogAttributeProfileCategory  # noqa: E402
from app.models.catalog_category import CatalogCategory  # noqa: E402
from app.models.catalog_product import CatalogProduct  # noqa: E402
from app.models.catalog_product_attribute_value import CatalogProductAttributeValue  # noqa: E402
import main  # noqa: E402,F401  (imports every model so all foreign-key tables are registered)
from app.services.builder_slot_packs import PC_SLOT_CATALOG_SLUGS  # noqa: E402

OLD_PROFILE_CODE = "pc_builder_specs"

# builder group code -> (profile code, profile name, builder slot slug)
SPLIT = {
    "cpu": ("processor", "Processor", "cpu"),
    "motherboard": ("motherboard", "Motherboard", "motherboard"),
    "memory": ("memory", "Memory (RAM)", "memory"),
    "graphics_card": ("graphics_card", "Graphics Card", "graphics-card"),
    "power_supply": ("power_supply", "Power Supply", "power-supply"),
    "casing": ("casing", "Casing", "casing"),  # profile already exists — group is added to it
    "cpu_cooler": ("cpu_cooler", "CPU Cooler", "cpu-cooler"),
    "storage": ("storage", "Storage (SSD/HDD)", "storage"),
    "monitor": ("monitor", "Monitor", "monitor"),
}


def main(apply: bool) -> None:
    db = SessionLocal()
    log = print if apply else (lambda *a: print("[dry-run]", *a))
    try:
        old = db.query(CatalogAttributeProfile).filter(CatalogAttributeProfile.code == OLD_PROFILE_CODE).first()

        # ---- 1. profiles + groups -------------------------------------------------
        profiles: dict[str, CatalogAttributeProfile] = {}
        for group_code, (code, name, _slot) in SPLIT.items():
            prof = db.query(CatalogAttributeProfile).filter(CatalogAttributeProfile.code == code).first()
            if prof is None:
                prof = CatalogAttributeProfile(
                    id=str(uuid.uuid4()),
                    name=name,
                    code=code,
                    description=f"{name} specifications, including the fields the Smart PC Builder rules read.",
                    sort_order=0,
                    is_active=True,
                )
                db.add(prof)
                db.flush()
                log(f"create profile {code} ({name})")
            profiles[group_code] = prof

        if old is not None:
            for group in db.query(CatalogAttributeGroup).filter(CatalogAttributeGroup.profile_id == old.id).all():
                target = profiles.get(group.code)
                if target is None:
                    continue  # e.g. the empty legacy "pc_builder" group — dropped below
                top = max(
                    (g.sort_order for g in db.query(CatalogAttributeGroup).filter(CatalogAttributeGroup.profile_id == target.id)),
                    default=0,
                )
                group.profile_id = target.id
                group.sort_order = top + 1
                log(f"move group {group.code} -> profile {target.code}")
        else:
            log("old profile pc_builder_specs not found — groups already split")

        # ---- 2/3. products + category scope --------------------------------------
        slug_to_group: dict[str, str] = {}
        for group_code, (_c, _n, slot) in SPLIT.items():
            for slug in PC_SLOT_CATALOG_SLUGS.get(slot, []):
                slug_to_group.setdefault(slug, group_code)
        categories = {c.slug: c for c in db.query(CatalogCategory).filter(CatalogCategory.slug.in_(list(slug_to_group))).all()}

        # Profiles this script created for the builder. A product sitting on one of these
        # (or on no profile / the old shared one) follows its catalog category. Casing and
        # Monitor already existed as profiles an admin may have chosen deliberately, so a
        # product on one of those is left alone.
        ours = {p.id for g, p in profiles.items() if g not in ("casing", "monitor")}
        movable = {None, old.id if old else None} | ours

        moved: Counter = Counter()
        for slug, cat in categories.items():
            target = profiles[slug_to_group[slug]]
            for product in db.query(CatalogProduct).filter(CatalogProduct.category_id == cat.id).all():
                if product.attribute_profile_id in movable:
                    if product.attribute_profile_id != target.id:
                        product.attribute_profile_id = target.id
                        moved[target.code] += 1
            exists = (
                db.query(CatalogAttributeProfileCategory)
                .filter(
                    CatalogAttributeProfileCategory.profile_id == target.id,
                    CatalogAttributeProfileCategory.category_id == cat.id,
                )
                .first()
            )
            if exists is None:
                db.add(CatalogAttributeProfileCategory(profile_id=target.id, category_id=cat.id))
                log(f"scope profile {target.code} to category {slug}")
        for code, n in moved.items():
            log(f"assign {n} product(s) to profile {code}")

        # Products still on the old profile but outside the builder categories: pick the
        # profile their stored values belong to (majority group), so nothing is left behind.
        db.flush()  # the session doesn't autoflush — make the assignments above visible to the query below
        if old is not None:
            leftovers = db.query(CatalogProduct).filter(CatalogProduct.attribute_profile_id == old.id).all()
            for product in leftovers:
                groups = Counter(
                    attr.group_id
                    for _pav, attr in db.query(CatalogProductAttributeValue, CatalogAttribute)
                    .join(CatalogAttribute, CatalogAttribute.id == CatalogProductAttributeValue.attribute_id)
                    .filter(CatalogProductAttributeValue.product_id == product.id)
                    .all()
                )
                target_id = None
                if groups:
                    top_group = db.get(CatalogAttributeGroup, groups.most_common(1)[0][0])
                    target_id = top_group.profile_id if top_group else None
                if target_id and target_id != old.id:
                    product.attribute_profile_id = target_id
                    log(f"product {product.name!r}: moved by its stored values")
                else:
                    log(f"product {product.name!r}: left on the old profile (no stored values to decide by)")

        # ---- 4. drop the old profile once nothing uses it ------------------------
        if old is not None:
            db.flush()
            still_products = db.query(CatalogProduct).filter(CatalogProduct.attribute_profile_id == old.id).count()
            groups_left = db.query(CatalogAttributeGroup).filter(CatalogAttributeGroup.profile_id == old.id).all()
            empty_groups = [g for g in groups_left if db.query(CatalogAttribute).filter(CatalogAttribute.group_id == g.id).count() == 0]
            if still_products == 0 and len(empty_groups) == len(groups_left):
                for g in groups_left:
                    db.delete(g)
                db.query(CatalogAttributeProfileCategory).filter(CatalogAttributeProfileCategory.profile_id == old.id).delete()
                db.delete(old)
                log("removed the now-empty profile pc_builder_specs")
            else:
                log(f"kept pc_builder_specs ({still_products} product(s), {len(groups_left)} group(s) still on it)")

        if apply:
            db.commit()
            print("Done.")
        else:
            db.rollback()
            print("Dry run only — nothing changed. Re-run with --apply.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main("--apply" in sys.argv)
