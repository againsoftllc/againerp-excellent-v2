"""Seed the Autology storefront catalog (categories, brands, products) into the API DB.

Source JSON is exported from the storefront's own seed data, so the shop's pages
and the admin catalog agree on one set of products:

    curl http://localhost:3002/api/dev/catalog-export
      > apps/api/scripts/data/autology_catalog.json

Usage (API container):

    python scripts/seed_autology_catalog.py
"""

from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.catalog_attribute_profile import CatalogAttributeProfile  # noqa: F401
from app.models.catalog_brand import CatalogBrand
from app.models.catalog_category import CatalogCategory
from app.models.catalog_product import CatalogProduct
from app.models.ecommerce_item import EcommerceItem
from app.models.ecommerce_item_category import EcommerceItemCategory
from app.services.ecommerce.ecommerce_item_service import EcommerceItemService
from app.services.seed_once import already_seeded, mark_seeded
from app.services.items.catalog_item_bridge import ensure_item_for_catalog_product

DATA_PATH = Path(__file__).resolve().parent / "data" / "excellent_catalog.json"

SITE_NAME = "Excellent Technology BD"
SKU_PREFIX = "EXT"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "item"


def _apply_path_depth(row: CatalogCategory, parent: CatalogCategory | None) -> None:
    if parent:
        row.parent_id = parent.id
        row.depth = parent.depth + 1
        row.path = f"{parent.path}{row.id}/"
    else:
        row.parent_id = None
        row.depth = 0
        row.path = f"/{row.id}/"


def _html_escape(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _short_html(name: str, features: list[str]) -> str:
    if features:
        items = "".join(f"<li>{_html_escape(line)}</li>" for line in features)
        return f"<ul>{items}</ul>"
    return f"<p>{_html_escape(name)}</p>"


def _full_html(product: dict) -> str:
    parts = [f"<h2>{_html_escape(product['name'])}</h2>"]
    para = (product.get("description") or "").strip()
    if para:
        parts.append(f"<p>{_html_escape(para)}</p>")
    features = product.get("specs") or []
    if features:
        items = "".join(f"<li>{_html_escape(line)}</li>" for line in features)
        parts.append(f"<h3>Key Features</h3><ul>{items}</ul>")
    for section in product.get("spec_sections") or []:
        rows = section.get("rows") or []
        if not rows:
            continue
        cells = "".join(
            f"<tr><th>{_html_escape(row[0])}</th><td>{_html_escape(row[1])}</td></tr>"
            for row in rows
            if len(row) >= 2
        )
        title = section.get("title") or "Specifications"
        parts.append(f"<h3>{_html_escape(title)}</h3><table><tbody>{cells}</tbody></table>")
    return "".join(parts)


def _specs_json(product: dict) -> str:
    """Storefront spec tables in the shape the admin product editor reads."""
    groups: list[dict] = []
    attrs: list[dict] = []
    for i, section in enumerate(product.get("spec_sections") or []):
        gid = f"g{i + 1}"
        groups.append({"id": gid, "name": section.get("title") or "Specifications"})
        for row in section.get("rows") or []:
            if len(row) < 2:
                continue
            label = str(row[0]).strip()
            value = str(row[1]).strip()
            if not label and not value:
                continue
            attrs.append({"groupId": gid, "name": label or "Spec", "value": value})

    # Facet attributes the PLP filters on (panel type, refresh rate, screen size).
    extra = {k: v for k, v in (product.get("attributes") or {}).items() if v not in (None, "")}
    if extra:
        gid = f"g{len(groups) + 1}"
        groups.append({"id": gid, "name": "Filters"})
        for key, value in extra.items():
            attrs.append(
                {
                    "groupId": gid,
                    "name": key.replace("_", " ").title(),
                    "value": str(value),
                }
            )
    return json.dumps({"customGroups": groups, "customAttrs": attrs})


def load_payload() -> dict:
    if not DATA_PATH.exists():
        raise SystemExit(
            f"Missing {DATA_PATH} — export it from the storefront first:\n"
            "  curl http://localhost:3002/api/dev/catalog-export "
            "> apps/api/scripts/data/autology_catalog.json"
        )
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def seed_categories(db: Session, rows: list[dict]) -> tuple[int, int]:
    """Create any category the storefront defines but the DB doesn't have yet.

    Insert-only: once a category row exists, this never touches it again, even
    if the bundled export's name, order or "show in top menu" flag changes.
    From that point the admin's Catalog → Categories screen is the only thing
    that edits it — this boots on every API start, so overwriting existing rows
    would silently revert whatever the admin last saved.
    """
    by_slug = {c.slug: c for c in db.query(CatalogCategory).all()}
    created = skipped = 0

    for order, item in enumerate(rows):
        if item["slug"] in by_slug:
            skipped += 1
            continue
        parent = by_slug.get(item["parent_slug"]) if item.get("parent_slug") else None
        row = CatalogCategory(
            id=str(uuid.uuid4()),
            name=item["name"],
            caption=item["name"],
            slug=item["slug"],
            sort_order=order,
            is_active=True,
            show_in_top_menu=bool(item.get("show_in_top_menu", True)),
            channel="catalog",
            meta_title=item.get("title") or f"{item['name']} Price in Bangladesh | {SITE_NAME}",
            meta_description=f"Buy {item['name']} online at {SITE_NAME}.",
        )
        db.add(row)
        db.flush()
        _apply_path_depth(row, parent)
        by_slug[row.slug] = row
        created += 1

    print(f"Categories created={created} already_existed={skipped}")
    return created, skipped


def purge_leftover_catalog_categories(db: Session, keep: set[str]) -> int:
    """Drop categories not in ``keep``. Not called automatically — see `main`."""
    ids = [
        row.id
        for row in db.query(CatalogCategory).filter(CatalogCategory.channel == "catalog").all()
        if row.slug not in keep
    ]
    if not ids:
        return 0

    db.query(CatalogCategory).filter(CatalogCategory.parent_id.in_(ids)).update(
        {CatalogCategory.parent_id: None},
        synchronize_session=False,
    )
    db.query(EcommerceItemCategory).filter(EcommerceItemCategory.category_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(EcommerceItem).filter(EcommerceItem.primary_category_id.in_(ids)).update(
        {EcommerceItem.primary_category_id: None},
        synchronize_session=False,
    )
    db.query(CatalogProduct).filter(CatalogProduct.category_id.in_(ids)).update(
        {CatalogProduct.category_id: None},
        synchronize_session=False,
    )
    db.query(CatalogCategory).filter(CatalogCategory.id.in_(ids)).delete(synchronize_session=False)
    return len(ids)


def seed_brands(db: Session, rows: list[dict]) -> tuple[int, int]:
    """Create any brand the storefront defines but the DB doesn't have yet.

    Insert-only, for the same reason as `seed_categories`: this boots on every
    API start, and the admin's Catalog → Brands screen owns these rows from the
    moment they exist.
    """
    by_slug = {b.slug: b for b in db.query(CatalogBrand).all()}
    by_name = {b.name.lower(): b for b in by_slug.values()}
    created = skipped = 0

    for i, item in enumerate(rows):
        if item["slug"] in by_slug or item["name"].lower() in by_name:
            skipped += 1
            continue
        row = CatalogBrand(
            id=str(uuid.uuid4()),
            name=item["name"],
            slug=item["slug"],
            is_active=True,
            channel="catalog",
            sort_order=i,
        )
        db.add(row)
        db.flush()
        by_slug[row.slug] = row
        by_name[row.name.lower()] = row
        created += 1

    print(f"Brands created={created} already_existed={skipped}")
    return created, skipped


def purge_leftover_catalog_brands(db: Session, keep: set[str]) -> int:
    """Drop brands not in ``keep``, moving their products to the kept brand of
    the same name. Not called automatically — see `main`."""
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
                {EcommerceItem.brand_id: target.id},
                synchronize_session=False,
            )
        else:
            db.query(CatalogProduct).filter(CatalogProduct.brand_id == row.id).update(
                {CatalogProduct.brand_id: None},
                synchronize_session=False,
            )
            db.query(EcommerceItem).filter(EcommerceItem.brand_id == row.id).update(
                {EcommerceItem.brand_id: None},
                synchronize_session=False,
            )

    db.query(CatalogBrand).filter(CatalogBrand.id.in_(leftover_ids)).delete(
        synchronize_session=False
    )
    return len(leftover_ids)


def _brand_for(db: Session, name: str, cache: dict[str, CatalogBrand]) -> CatalogBrand:
    key = (name or SITE_NAME).strip()
    found = cache.get(key.lower())
    if found:
        return found
    slug = _slugify(key)
    row = (
        db.query(CatalogBrand)
        .filter(CatalogBrand.slug == slug, CatalogBrand.channel == "catalog")
        .first()
    )
    if row is None:
        row = CatalogBrand(
            id=str(uuid.uuid4()),
            name=key,
            slug=slug,
            is_active=True,
            channel="catalog",
        )
        db.add(row)
        db.flush()
    cache[key.lower()] = row
    return row


def _unique_sku(db: Session, slug: str) -> str:
    base = re.sub(r"[^A-Z0-9-]+", "-", slug.upper()).strip("-")[:40] or "SKU"
    sku = f"{SKU_PREFIX}-{base}"
    exists = (
        db.query(CatalogProduct)
        .filter(CatalogProduct.sku == sku, CatalogProduct.slug != slug)
        .first()
    )
    if not exists:
        return sku
    return f"{SKU_PREFIX}-{slug[:24].upper()}-{uuid.uuid4().hex[:6].upper()}"


def seed_products(db: Session, rows: list[dict], categories: list[dict]) -> tuple[int, int]:
    """Create any product the storefront defines but the DB doesn't have yet.

    Insert-only, for the same reason as `seed_categories`: this boots on every
    API start, and once a product exists the admin's Catalog → Products screen
    owns its price, stock, description and everything else about it.
    """
    cats = {c.slug: c for c in db.query(CatalogCategory).all()}
    parent_of = {c["slug"]: c.get("parent_slug") for c in categories}
    brands: dict[str, CatalogBrand] = {b.name.lower(): b for b in db.query(CatalogBrand).all()}
    existing_slugs = {slug for (slug,) in db.query(CatalogProduct.slug).all()}
    svc = EcommerceItemService(db)
    created = skipped = 0

    for index, item in enumerate(rows):
        if item["slug"] in existing_slugs:
            skipped += 1
            continue
        cat = cats.get(str(item.get("category") or ""))
        if cat is None:
            print(f"  skip {item['slug']}: missing category {item.get('category')}")
            continue
        brand = _brand_for(db, item.get("brand") or SITE_NAME, brands)
        product = CatalogProduct(id=str(uuid.uuid4()), slug=item["slug"])
        db.add(product)
        created += 1

        gallery = item.get("gallery") or []
        thumbnail = item.get("image") or (gallery[0] if gallery else None)
        out_of_stock = bool(item.get("out_of_stock"))

        product.name = item["name"]
        product.sku = _unique_sku(db, item["slug"])
        product.price = Decimal(str(item["price"]))
        product.compare_at_price = (
            Decimal(str(item["price_old"])) if item.get("price_old") else None
        )
        product.stock = 0 if out_of_stock else 20 + index
        product.track_quantity = True
        product.stock_status = "out_of_stock" if out_of_stock else "in_stock"
        product.status = "published"
        product.product_type = "simple"
        product.visibility = "public"
        product.brand = brand.name
        product.brand_id = brand.id
        product.category = cat.name
        product.category_id = cat.id
        product.thumbnail = thumbnail
        product.gallery_json = json.dumps(gallery) if gallery else None
        product.short_description = _short_html(item["name"], item.get("specs") or [])
        product.description = _full_html(item)
        product.seo_title = f"{item['name']} Price in Bangladesh | {SITE_NAME}"
        product.seo_description = (item.get("description") or item["name"])[:500]
        product.custom_specs_json = _specs_json(item)
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
        ec.specifications_json = product.custom_specs_json
        ec.publish_status = "published"
        ec.visibility = "public"
        ec.is_active = True
        ec.featured = index < 12 and bool(item.get("price_old"))
        db.flush()

        item_id = product.item_id or product.id
        extra_ids = [cat.id]
        parent_slug = parent_of.get(cat.slug)
        if parent_slug and parent_slug in cats:
            extra_ids.append(cats[parent_slug].id)
        svc.replace_categories(
            item_id,
            extra_ids,
            primary_category_id=cat.id,
            company_id=product.company_id,
        )

    print(f"Products created={created} already_existed={skipped}")
    return created, skipped


def main() -> None:
    payload = load_payload()
    db = SessionLocal()
    try:
        has_data = db.query(CatalogCategory).filter(CatalogCategory.channel == "catalog").first() is not None
        if already_seeded(db, "excellent_catalog_seeded", has_data=has_data):
            print(f"{SITE_NAME} catalog already seeded; skipping (admin owns it now).")
            return
        seed_categories(db, payload["categories"])
        db.flush()
        seed_brands(db, payload["brands"])
        db.flush()
        seed_products(db, payload["products"], payload["categories"])
        mark_seeded(db, "excellent_catalog_seeded")
        db.commit()
        print(f"{SITE_NAME} catalog seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
