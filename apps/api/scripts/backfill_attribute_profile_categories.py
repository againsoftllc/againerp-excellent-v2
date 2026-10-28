#!/usr/bin/env python3
"""One-time backfill for `catalog_attribute_profile_categories`.

Seeds each attribute profile's category scope from the categories its
existing products actually live in (primary category + any secondary
category tags), so live storefront facets narrow to the right category
immediately instead of every profile starting unscoped.

An unscoped profile (no rows here) still shows its filters everywhere — the
same as before this feature existed — so skipping/re-running this is safe.

Rule: for a profile, collect every category touched by its products. Drop
any ROOT-level category (depth 0) from that set as long as a more specific
(non-root) category is also present — e.g. a product tagged both the root
"Component" and its child "Casing" keeps only "Casing". This is what keeps
a "Casing Specs" profile scoped to "Casing" (and any of its own sub-levels)
rather than also matching the broad parent "Component" it happens to
inherit into, without collapsing a whole multi-level chain down to just its
single deepest node.

Safe to re-run: existing links for a profile are replaced, not stacked.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models.catalog_attribute_profile import CatalogAttributeProfile  # noqa: E402
from app.models.catalog_attribute_profile_category import CatalogAttributeProfileCategory  # noqa: E402
from app.models.catalog_category import CatalogCategory  # noqa: E402
from app.models.catalog_product import CatalogProduct  # noqa: E402
from app.models.ecommerce_item import EcommerceItem  # noqa: E402
from app.models.ecommerce_item_category import EcommerceItemCategory  # noqa: E402


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        categories = {c.id: c for c in db.query(CatalogCategory).all()}

        def drop_broad_roots(category_ids: Set[str]) -> Set[str]:
            known = {cid for cid in category_ids if cid in categories}
            specific = {cid for cid in known if categories[cid].depth > 0}
            return specific or known

        profiles = db.query(CatalogAttributeProfile).all()
        total_linked = 0
        for profile in profiles:
            product_ids = [
                pid
                for (pid,) in db.query(CatalogProduct.id)
                .filter(CatalogProduct.attribute_profile_id == profile.id)
                .all()
            ]
            if not product_ids:
                continue

            items = (
                db.query(EcommerceItem.item_id, EcommerceItem.primary_category_id)
                .filter(EcommerceItem.catalog_product_id.in_(product_ids))
                .all()
            )
            item_ids = [i.item_id for i in items]
            category_ids: Set[str] = {i.primary_category_id for i in items if i.primary_category_id}
            if item_ids:
                secondary = (
                    db.query(EcommerceItemCategory.category_id)
                    .filter(EcommerceItemCategory.item_id.in_(item_ids))
                    .all()
                )
                category_ids |= {c.category_id for c in secondary if c.category_id}

            scoped = drop_broad_roots(category_ids)
            if not scoped:
                continue

            db.query(CatalogAttributeProfileCategory).filter(
                CatalogAttributeProfileCategory.profile_id == profile.id,
            ).delete(synchronize_session=False)
            for category_id in scoped:
                db.add(
                    CatalogAttributeProfileCategory(profile_id=profile.id, category_id=category_id),
                )
            names = ", ".join(categories[c].name for c in scoped if c in categories)
            print(f"{profile.name}: scoped to [{names}]")
            total_linked += len(scoped)

        db.commit()
        print(f"Done. {total_linked} profile-category link(s) written.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
