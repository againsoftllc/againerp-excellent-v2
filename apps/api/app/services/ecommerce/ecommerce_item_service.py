"""Ecommerce item extension — sync, publish, storefront resolution."""

from __future__ import annotations

import time
from datetime import datetime

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.catalog_product_special import (
    CatalogProductSpecial,
    resolve_active_special,
)
from app.models.catalog_product import CatalogProduct
from app.models.catalog_product_media import CatalogProductMedia
from app.models.catalog_product_variant import CatalogProductVariant
from app.models.ecommerce_item import EcommerceItem
from app.models.ecommerce_item_category import EcommerceItemCategory
from app.models.ecommerce_item_media import EcommerceItemMedia
from app.models.media import Media
from app.services.ecommerce.constants import (
    CATALOG_STATUS_TO_PUBLISH,
    STOREFRONT_LIVE_STATUSES,
    PREVIEW_VISIBLE_STATUSES,
    PUBLISH_TO_CATALOG_STATUS,
)
from app.services.ecommerce.publish_service import EcommercePublishService
from app.services.items.catalog_item_bridge import ensure_item_for_catalog_product
from app.services.items.item_identity_service import ItemIdentityService


def _load_tags(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _dump_tags(tags: List[str]) -> str:
    return json.dumps(tags or [])


_STATUS_CACHE: dict[str, object] = {}
_STATUS_CACHE_AT: float = 0.0
_STATUS_CACHE_TTL = 30.0


def stock_status_flags(code: str):
    """Flags for a stock status code, or None if unknown.

    Cached process-wide for a few seconds: this runs once per product inside
    storefront list loops, so a query (let alone a session) per call would be
    N+1. A new or edited status shows up within the TTL.
    """
    global _STATUS_CACHE, _STATUS_CACHE_AT
    now = time.monotonic()
    # `_STATUS_CACHE_AT` starts at 0.0, so the very first call already exceeds
    # the TTL and loads — an `or not _STATUS_CACHE` here would additionally
    # treat "loaded, but there are zero custom statuses" as "never loaded",
    # re-querying (with a brand new session) on every single call instead of
    # once per TTL window, which is what actually happens on a fresh install
    # before any custom stock status is configured.
    if now - _STATUS_CACHE_AT > _STATUS_CACHE_TTL:
        from app.database import SessionLocal
        from app.models.catalog_stock_status import CatalogStockStatus

        db = SessionLocal()
        try:
            _STATUS_CACHE = {r.code: r for r in db.query(CatalogStockStatus).all()}
            _STATUS_CACHE_AT = now
        except Exception:
            return None
        finally:
            db.close()
    return _STATUS_CACHE.get(code)


def _resolve_storefront_in_stock(
    *,
    stock: int,
    track_quantity: bool,
    stock_status: Optional[str],
) -> bool:
    status = (stock_status or "").strip().lower() or None

    # No status = "Auto (based on quantity)".
    if status is None:
        return stock > 0 if track_quantity else True

    flags = stock_status_flags(status)
    if flags is not None:
        if not flags.counts_as_in_stock:
            return False
        return stock > 0 if (track_quantity and flags.tracks_quantity) else True

    # Unknown code (status row deleted out from under a product) — fall back to
    # the original built-in behaviour rather than claiming it is in stock.
    if status in ("out_of_stock", "coming_soon"):
        return False
    return stock > 0 if track_quantity else True


@dataclass(frozen=True)
class StorefrontProductView:
    id: str
    item_id: str
    slug: str
    name: str
    price: Decimal
    compare_at_price: Optional[Decimal]
    stock: int
    track_quantity: bool
    stock_status: Optional[str]
    contact_phone: Optional[str]
    brand: str
    category: str
    thumbnail: Optional[str]
    in_stock: bool
    short_description: Optional[str] = None
    featured: bool = False
    sku: Optional[str] = None
    model: Optional[str] = None
    category_slug: str = ""
    # More than one variant means the shopper has a choice to make first.
    has_options: bool = False
    # when the listing or its catalog product last changed (sitemap lastmod)
    updated_at: Optional[datetime] = None


class EcommerceItemService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._specials_by_product: Optional[dict[str, list[CatalogProductSpecial]]] = None
        self._variant_counts: Optional[dict[str, int]] = None
        # Per-id caches for resolve_storefront_from_ecommerce — a list endpoint
        # calls that once per row, so a fresh .get() per lookup here is N+1.
        # preload_for_items() warms these in one query each; a cache miss
        # (e.g. resolving a single product) still falls back to .get().
        self._product_cache: dict[str, Optional[CatalogProduct]] = {}
        self._item_cache: dict[str, Optional["Item"]] = {}
        self._brand_cache: dict[str, Optional["CatalogBrand"]] = {}
        self._category_cache: dict[str, Optional["CatalogCategory"]] = {}

    def preload_for_items(self, rows: list[EcommerceItem]) -> None:
        """Batch-fetch everything resolve_storefront_from_ecommerce needs for a
        whole list of rows in four queries total, instead of up to four
        queries per row."""
        from app.models.item import Item
        from app.models.catalog_brand import CatalogBrand
        from app.models.catalog_category import CatalogCategory

        def _fetch(model, ids: set[str], cache: dict) -> None:
            missing = [i for i in ids if i not in cache]
            if not missing:
                return
            for row in self._db.query(model).filter(model.id.in_(missing)).all():
                cache[row.id] = row
            for i in missing:
                cache.setdefault(i, None)

        _fetch(
            CatalogProduct,
            {r.catalog_product_id for r in rows if r.catalog_product_id},
            self._product_cache,
        )
        _fetch(Item, {r.item_id for r in rows if r.item_id}, self._item_cache)
        _fetch(CatalogBrand, {r.brand_id for r in rows if r.brand_id}, self._brand_cache)
        _fetch(
            CatalogCategory,
            {r.primary_category_id for r in rows if r.primary_category_id},
            self._category_cache,
        )

    def _get_product(self, product_id: Optional[str]) -> Optional[CatalogProduct]:
        if not product_id:
            return None
        if product_id not in self._product_cache:
            self._product_cache[product_id] = self._db.get(CatalogProduct, product_id)
        return self._product_cache[product_id]

    def _get_item(self, item_id: Optional[str]):
        from app.models.item import Item

        if not item_id:
            return None
        if item_id not in self._item_cache:
            self._item_cache[item_id] = self._db.get(Item, item_id)
        return self._item_cache[item_id]

    def _get_brand(self, brand_id: Optional[str]):
        from app.models.catalog_brand import CatalogBrand

        if not brand_id:
            return None
        if brand_id not in self._brand_cache:
            self._brand_cache[brand_id] = self._db.get(CatalogBrand, brand_id)
        return self._brand_cache[brand_id]

    def _get_category(self, category_id: Optional[str]):
        from app.models.catalog_category import CatalogCategory

        if not category_id:
            return None
        if category_id not in self._category_cache:
            self._category_cache[category_id] = self._db.get(CatalogCategory, category_id)
        return self._category_cache[category_id]

    def _variant_count_map(self) -> dict[str, int]:
        """Variants per product, loaded once — this is read inside list loops, so
        a per-item COUNT would be N+1."""
        if self._variant_counts is None:
            rows = (
                self._db.query(
                    CatalogProductVariant.product_id,
                    func.count(CatalogProductVariant.id),
                )
                .group_by(CatalogProductVariant.product_id)
                .all()
            )
            self._variant_counts = {pid: int(count) for pid, count in rows}
        return self._variant_counts

    def _specials_map(self) -> dict[str, list[CatalogProductSpecial]]:
        """Loaded once per service instance — resolve_storefront_from_ecommerce is
        called in list loops, so a per-item query would be N+1."""
        if self._specials_by_product is None:
            grouped: dict[str, list[CatalogProductSpecial]] = {}
            for row in self._db.query(CatalogProductSpecial).all():
                grouped.setdefault(row.product_id, []).append(row)
            self._specials_by_product = grouped
        return self._specials_by_product

    def active_special_price(self, catalog_product_id: Optional[str]):
        """Price of the special that is live right now, or None."""
        if not catalog_product_id:
            return None
        rows = self._specials_map().get(catalog_product_id)
        if not rows:
            return None
        active = resolve_active_special(rows)
        return active.price if active else None

    def get_by_item_id(self, item_id: str) -> Optional[EcommerceItem]:
        return (
            self._db.query(EcommerceItem)
            .filter(EcommerceItem.item_id == item_id)
            .first()
        )

    def get_by_catalog_product_id(self, product_id: str) -> Optional[EcommerceItem]:
        return (
            self._db.query(EcommerceItem)
            .filter(EcommerceItem.catalog_product_id == product_id)
            .first()
        )

    def ensure_draft_for_catalog_product(self, product: CatalogProduct) -> EcommerceItem:
        """Create or update ecommerce extension as draft — does NOT auto-publish."""
        item_id = ensure_item_for_catalog_product(self._db, product)
        row = self.get_by_item_id(item_id)
        if not row:
            row = EcommerceItem(
                item_id=item_id,
                company_id=product.company_id,
                catalog_product_id=product.id,
                publish_status="draft",
                slug=product.slug,
            )
            self._db.add(row)
            self._db.flush()
        return self.sync_content_from_catalog(product, row=row, mirror_publish=True)

    def sync_content_from_catalog(
        self,
        product: CatalogProduct,
        *,
        row: Optional[EcommerceItem] = None,
        mirror_publish: bool = True,
    ) -> EcommerceItem:
        """Push catalog merchandising fields into ecommerce_items (not identity)."""
        item_id = product.item_id or ensure_item_for_catalog_product(self._db, product)
        ec = row or self.get_by_item_id(item_id)
        if not ec:
            ec = EcommerceItem(
                item_id=item_id,
                company_id=product.company_id,
                catalog_product_id=product.id,
                publish_status="draft",
                slug=product.slug,
            )
            self._db.add(ec)
            self._db.flush()

        ec.catalog_product_id = product.id
        ec.slug = product.slug
        ec.visibility = product.visibility
        ec.short_description = product.short_description
        ec.full_description = product.description
        ec.specifications_json = product.custom_specs_json
        ec.primary_category_id = product.category_id
        ec.brand_id = product.brand_id
        ec.seo_title = product.seo_title
        ec.seo_description = product.seo_description
        ec.seo_keywords_json = product.tags_json or "[]"
        ec.schema_ready = bool(product.seo_title and product.seo_description)
        ec.selling_price = product.price
        ec.compare_at_price = product.compare_at_price
        # A live OpenCart-style special overrides the shop price; storefront
        # pricing and cart already honour ec.special_price.
        specials = (
            self._db.query(CatalogProductSpecial)
            .filter(CatalogProductSpecial.product_id == product.id)
            .all()
        )
        active = resolve_active_special(specials)
        ec.special_price = active.price if active else None
        ec.thumbnail_url = product.thumbnail
        ec.sort_order = 0

        if mirror_publish:
            ec.publish_status = CATALOG_STATUS_TO_PUBLISH.get(product.status, "draft")
            if product.visibility == "private" and ec.publish_status == "published":
                ec.publish_status = "hidden"

        ec.is_active = ec.publish_status == "published"
        self._sync_categories(product, item_id)
        self._sync_media_from_catalog(product, item_id)
        self._db.flush()
        return ec

    def sync_to_catalog_product(self, ec: EcommerceItem, product: CatalogProduct) -> None:
        """Mirror ecommerce fields back to catalog_products for backward-compatible APIs."""
        product.slug = ec.slug
        product.short_description = ec.short_description
        product.description = ec.full_description
        product.custom_specs_json = ec.specifications_json
        product.category_id = ec.primary_category_id
        product.brand_id = ec.brand_id
        product.seo_title = ec.seo_title
        product.seo_description = ec.seo_description
        product.tags_json = ec.seo_keywords_json
        product.price = ec.selling_price
        product.compare_at_price = ec.compare_at_price
        product.thumbnail = ec.thumbnail_url
        product.visibility = ec.visibility
        product.status = PUBLISH_TO_CATALOG_STATUS.get(ec.publish_status, "draft")
        self._db.flush()

    def publish(self, item_id: str) -> EcommerceItem:
        return EcommercePublishService(self._db).publish(item_id)

    def unpublish(self, item_id: str, *, hidden: bool = False) -> EcommerceItem:
        return EcommercePublishService(self._db).unpublish(item_id, hidden=hidden)

    def archive(self, item_id: str) -> EcommerceItem:
        return EcommercePublishService(self._db).archive(item_id)

    def submit_for_review(self, item_id: str) -> EcommerceItem:
        return EcommercePublishService(self._db).submit_for_review(item_id)

    def reject_review(self, item_id: str) -> EcommerceItem:
        return EcommercePublishService(self._db).reject_review(item_id)

    def restore(self, item_id: str) -> EcommerceItem:
        return EcommercePublishService(self._db).restore(item_id)

    def list_storefront_items(
        self,
        *,
        search: Optional[str] = None,
        category_id: Optional[str] = None,
        featured: Optional[bool] = None,
        include_private: bool = False,
    ) -> list[EcommerceItem]:
        """Published ecommerce rows only — storefront never lists from catalog_products."""
        from app.models.item import Item

        query = (
            self._db.query(EcommerceItem)
            .join(Item, Item.id == EcommerceItem.item_id)
            .filter(
                EcommerceItem.publish_status.in_(
                    PREVIEW_VISIBLE_STATUSES if include_private else STOREFRONT_LIVE_STATUSES
                ),
            )
        )
        if not include_private:
            # Private products stay out of the public shop entirely; only a
            # signed-in staff member previewing the site may see them.
            query = query.filter(EcommerceItem.visibility == "public")
        if featured is not None:
            query = query.filter(EcommerceItem.featured == featured)
        if category_id:
            query = query.filter(EcommerceItem.primary_category_id == category_id)
        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                (EcommerceItem.slug.ilike(term))
                | (Item.name.ilike(term))
                | (Item.sku.ilike(term)),
            )
        return query.order_by(EcommerceItem.sort_order, EcommerceItem.updated_at.desc()).all()

    def resolve_storefront_from_ecommerce(
        self,
        ec: EcommerceItem,
        *,
        allow_preview: bool = False,
    ) -> Optional[StorefrontProductView]:
        """Build storefront view from ecommerce_items — catalog used only for stock bridge."""
        publish_svc = EcommercePublishService(self._db)
        if not publish_svc.is_storefront_live(ec):
            # A staff preview may still render a Private ("hidden") product; the
            # caller has already checked who is asking.
            if not (allow_preview and ec.publish_status in PREVIEW_VISIBLE_STATUSES):
                return None

        product = self._get_product(ec.catalog_product_id)

        identity = ItemIdentityService(self._db)
        item = self._get_item(ec.item_id)
        name = ec.slug
        sku: Optional[str] = None
        if product:
            # Pass the already-loaded item (keyed by the product's own
            # item_id, same id resolve_identity would fetch itself) so this
            # doesn't re-query it — the two ids coincide in the normal case.
            resolved = identity.resolve_identity(product, item=self._get_item(product.item_id))
            name = resolved["name"]
            sku = (resolved.get("sku") or product.sku or "").strip() or None
        if item:
            name = item.name if not product else name
            sku = (item.sku or sku or "").strip() or None
        if not name:
            name = ec.slug

        brand_name = "Unknown"
        category_name = "Uncategorized"
        category_slug = ""
        if ec.brand_id:
            brand = self._get_brand(ec.brand_id)
            if brand:
                brand_name = brand.name
        elif product and product.brand:
            brand_name = product.brand

        if ec.primary_category_id:
            cat = self._get_category(ec.primary_category_id)
            if cat:
                category_name = cat.name
                category_slug = cat.slug or ""
        elif product and product.category:
            category_name = product.category

        stock = product.stock if product else 0
        track_quantity = product.track_quantity if product else True
        stock_status = product.stock_status if product else None
        contact_phone = getattr(product, "contact_phone", None) if product else None

        # A special price wins over the list price, but only while its date window
        # is open — so resolve it per request rather than trusting the cached column.
        effective_price = ec.selling_price
        specials = self._specials_map().get(ec.catalog_product_id or "")
        if specials:
            active = resolve_active_special(specials)
            if active is not None:
                effective_price = active.price
        elif ec.special_price is not None:
            effective_price = ec.special_price

        in_stock = _resolve_storefront_in_stock(
            stock=stock,
            track_quantity=track_quantity,
            stock_status=stock_status,
        )

        catalog_id = ec.catalog_product_id or ec.item_id

        return StorefrontProductView(
            id=catalog_id,
            item_id=ec.item_id,
            slug=ec.slug,
            name=name,
            price=effective_price,
            compare_at_price=ec.compare_at_price,
            stock=stock,
            track_quantity=track_quantity,
            stock_status=stock_status,
            contact_phone=contact_phone,
            brand=brand_name,
            category=category_name,
            thumbnail=ec.thumbnail_url,
            in_stock=in_stock,
            short_description=ec.short_description,
            featured=bool(ec.featured),
            sku=sku,
            model=(product.model or None) if product else None,
            category_slug=category_slug,
            has_options=self._variant_count_map().get(catalog_id, 0) > 1,
        )

    def is_storefront_visible(self, product: CatalogProduct, ec: Optional[EcommerceItem]) -> bool:
        if ec:
            return EcommercePublishService(self._db).is_storefront_live(ec)
        return False

    def resolve_storefront_product(self, product: CatalogProduct) -> Optional[StorefrontProductView]:
        ec = self.get_by_item_id(product.item_id) if product.item_id else self.get_by_catalog_product_id(product.id)
        if not ec:
            return None
        return self.resolve_storefront_from_ecommerce(ec)

    def _sync_categories(self, product: CatalogProduct, item_id: str) -> None:
        if not product.category_id:
            return
        existing = (
            self._db.query(EcommerceItemCategory)
            .filter(
                EcommerceItemCategory.item_id == item_id,
                EcommerceItemCategory.category_id == product.category_id,
            )
            .first()
        )
        if not existing:
            self._db.add(
                EcommerceItemCategory(
                    item_id=item_id,
                    company_id=product.company_id,
                    category_id=product.category_id,
                    is_primary=True,
                    sort_order=0,
                ),
            )
        else:
            existing.is_primary = True

        (
            self._db.query(EcommerceItemCategory)
            .filter(
                EcommerceItemCategory.item_id == item_id,
                EcommerceItemCategory.category_id != product.category_id,
            )
            .update({EcommerceItemCategory.is_primary: False}, synchronize_session=False)
        )

    def _sync_media_from_catalog(self, product: CatalogProduct, item_id: str) -> None:
        links = (
            self._db.query(CatalogProductMedia, Media)
            .join(Media, Media.id == CatalogProductMedia.media_id)
            .filter(CatalogProductMedia.product_id == product.id)
            .order_by(CatalogProductMedia.sort_order)
            .all()
        )
        if not links:
            return

        # The card thumbnail must be the product itself, so the featured media is
        # the first *image* in order. A video pinned first would otherwise win:
        # its poster frame is an ordinary .jpg, so nothing downstream can tell it
        # apart from a product photo.
        featured_media_id = next(
            (link.media_id for link, media in links if media.media_type == "image"),
            None,
        )

        for idx, (link, media) in enumerate(links):
            row = (
                self._db.query(EcommerceItemMedia)
                .filter(
                    EcommerceItemMedia.item_id == item_id,
                    EcommerceItemMedia.media_id == link.media_id,
                )
                .first()
            )
            if not row:
                row = EcommerceItemMedia(
                    item_id=item_id,
                    company_id=product.company_id,
                    media_id=link.media_id,
                )
                self._db.add(row)
            row.sort_order = link.sort_order if link.sort_order else idx
            row.is_primary = link.is_primary or idx == 0
            row.is_featured = link.media_id == featured_media_id
            if row.is_featured and media.url:
                ec = self.get_by_item_id(item_id)
                if ec:
                    ec.featured_media_id = link.media_id
                    # Always mirror featured Media Library URL onto ecommerce thumbnail
                    # so storefront does not keep stale seed placeholders (picsum).
                    ec.thumbnail_url = media.url
                    if not product.thumbnail or "picsum.photos" in (product.thumbnail or ""):
                        product.thumbnail = media.url

    def replace_categories(
        self,
        item_id: str,
        category_ids: List[str],
        *,
        primary_category_id: Optional[str] = None,
        company_id: str = "default",
    ) -> None:
        self._db.query(EcommerceItemCategory).filter(EcommerceItemCategory.item_id == item_id).delete()
        primary = primary_category_id or (category_ids[0] if category_ids else None)
        for idx, cat_id in enumerate(category_ids):
            self._db.add(
                EcommerceItemCategory(
                    item_id=item_id,
                    company_id=company_id,
                    category_id=cat_id,
                    is_primary=cat_id == primary,
                    sort_order=idx,
                ),
            )
        ec = self.get_by_item_id(item_id)
        if ec and primary:
            ec.primary_category_id = primary
        self._db.flush()
