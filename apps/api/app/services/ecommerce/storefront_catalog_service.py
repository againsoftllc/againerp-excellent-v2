"""Storefront product catalog — queries ecommerce_items only (STEP 04)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, desc, func, literal, or_
from sqlalchemy.orm import Session

from app.models.catalog_brand import CatalogBrand
from app.models.catalog_category import CatalogCategory
from app.models.catalog_product import CatalogProduct
from app.models.catalog_attribute import CatalogAttribute
from app.models.catalog_attribute_group import CatalogAttributeGroup
from app.models.catalog_attribute_profile_category import CatalogAttributeProfileCategory
from app.models.catalog_filter import CatalogFilter
from app.models.catalog_product_attribute_value import CatalogProductAttributeValue
from app.models.catalog_product_related import list_related_ids
from app.models.commerce_order_item import CommerceOrderItem
from app.models.ecommerce_item import EcommerceItem
from app.models.ecommerce_item_category import EcommerceItemCategory
from app.models.item import Item
from app.schemas.attribute_profile import parse_json_list
from app.services.ecommerce.constants import STOREFRONT_LIVE_STATUSES
from app.services.ecommerce.constants import PREVIEW_VISIBLE_STATUSES
from app.services.ecommerce.ecommerce_item_service import EcommerceItemService, StorefrontProductView


SORT_NEWEST = "newest"
SORT_PRICE_ASC = "price_asc"
SORT_PRICE_DESC = "price_desc"
SORT_BESTSELLING = "bestselling"
SORT_FEATURED = "featured"


_SEARCH_STRIP = re.compile(r"[\"'“”″ʺ(),|/]+")


def _search_clause(search: str):
    """Word-based product search over name, slug, SKU and SEO title, in any order.

    Words with a digit (model codes and sizes: K202Q, C6, AC1200, 19.5) must all match;
    of the other words about 60% must — so a shop's own spelling of a product
    ("Acer K202Q Bi 19.5 Inch HD Monitor", "… AC1200 Mbps … Router") still finds it."""
    fields = (EcommerceItem.slug, Item.name, Item.sku, EcommerceItem.seo_title)
    phrase = f"%{search.strip()}%"
    whole = or_(*(f.ilike(phrase) for f in fields))
    words = [w for w in _SEARCH_STRIP.sub(" ", search).split() if len(w) > 1 or w.isdigit()][:12]
    if len(words) < 2:
        return whole

    def hit(word: str):
        variants = [word]
        if word.lower() in ("inch", "inches", "in"):
            variants = ["inch", '"']  # names write 21.5", slugs write 21-5-inch
        return or_(*(f.ilike(f"%{v}%") for f in fields for v in variants))

    # A model code mixes letters and digits (K202Q, X50, AC1200, 1008a, 320Hz): one must match.
    models = [w for w in words if any(ch.isdigit() for ch in w) and any(ch.isalpha() for ch in w)]
    score = sum((case((hit(w), 1), else_=0) for w in words), literal(0))
    need = max(2, -(-len(words) * 6 // 10))  # ceil(60%) of the words
    fuzzy = score >= need
    if models:
        fuzzy = and_(or_(*(hit(w) for w in models)), fuzzy)
    return or_(whole, fuzzy)


def _search_rank(search: str):
    """Best match first: the whole phrase, then whole-word hits in the slug (C6 beats C64), then any hit."""
    fields = (EcommerceItem.slug, Item.name, Item.sku, EcommerceItem.seo_title)
    phrase = f"%{search.strip()}%"
    words = [w for w in _SEARCH_STRIP.sub(" ", search).split() if len(w) > 1 or w.isdigit()][:12]
    rank = case((or_(*(f.ilike(phrase) for f in fields)), 100), else_=0)
    for w in words:
        token = re.sub(r"[^a-z0-9]+", "-", w.lower()).strip("-")
        if not token:
            continue
        exact = or_(EcommerceItem.slug.ilike(f"%-{token}-%"), EcommerceItem.slug.ilike(f"{token}-%"), EcommerceItem.slug.ilike(f"%-{token}"))
        rank = rank + case((exact, 3), else_=0) + case((or_(*(f.ilike(f"%{w}%") for f in fields)), 1), else_=0)
    return rank


@dataclass(frozen=True)
class StorefrontListResult:
    items: List[StorefrontProductView]
    total: int


class StorefrontCatalogService:
    def __init__(self, db: Session, *, include_private: bool = False) -> None:
        self._db = db
        self._items = EcommerceItemService(db)
        # Set only for a signed-in staff member previewing the shop, so a
        # Published + Private product ("hidden") is reachable before going live.
        self._include_private = include_private

    def _base_query(self):
        query = (
            self._db.query(EcommerceItem)
            .join(Item, Item.id == EcommerceItem.item_id)
            .filter(
                EcommerceItem.publish_status.in_(
                    PREVIEW_VISIBLE_STATUSES if self._include_private else STOREFRONT_LIVE_STATUSES
                ),
            )
        )
        if not self._include_private:
            query = query.filter(EcommerceItem.visibility == "public")
        return query

    def _apply_filters(
        self,
        query,
        *,
        search: Optional[str] = None,
        category_id: Optional[str] = None,
        category_slug: Optional[str] = None,
        brand_id: Optional[str] = None,
        brand_slug: Optional[str] = None,
        brand_slugs: Optional[List[str]] = None,
        featured: Optional[bool] = None,
        on_sale: Optional[bool] = None,
        price_min: Optional[Decimal] = None,
        price_max: Optional[Decimal] = None,
        in_stock: Optional[bool] = None,
        attribute_filters: Optional[Dict[str, List[str]]] = None,
    ):
        if category_slug and not category_id:
            from sqlalchemy import case

            cat = (
                self._db.query(CatalogCategory)
                .filter(CatalogCategory.slug == category_slug)
                .order_by(
                    case((CatalogCategory.channel == "catalog", 0), else_=1),
                    CatalogCategory.sort_order.asc(),
                )
                .first()
            )
            if cat:
                category_id = cat.id
        if brand_slug and not brand_id:
            brand = (
                self._db.query(CatalogBrand)
                .filter(CatalogBrand.slug == brand_slug)
                .first()
            )
            if brand:
                brand_id = brand.id

        if search:
            query = query.filter(_search_clause(search))
        if category_id:
            # A section page lists its whole branch — "Laptop" shows every laptop,
            # not only the ones pinned directly on the parent.
            category_ids = self._category_branch_ids(category_id)
            query = query.filter(
                (EcommerceItem.primary_category_id.in_(category_ids))
                | EcommerceItem.item_id.in_(
                    self._db.query(EcommerceItemCategory.item_id).filter(
                        EcommerceItemCategory.category_id.in_(category_ids),
                    ),
                ),
            )
        if brand_slugs:
            brand_ids = [
                b.id
                for b in self._db.query(CatalogBrand)
                .filter(CatalogBrand.slug.in_(brand_slugs))
                .all()
            ]
            query = query.filter(EcommerceItem.brand_id.in_(brand_ids or ["__none__"]))
        elif brand_id:
            query = query.filter(EcommerceItem.brand_id == brand_id)
        if featured is not None:
            query = query.filter(EcommerceItem.featured == featured)
        if on_sale:
            query = query.filter(
                EcommerceItem.compare_at_price.isnot(None),
                EcommerceItem.compare_at_price > EcommerceItem.selling_price,
            )
        if price_min is not None:
            query = query.filter(EcommerceItem.selling_price >= price_min)
        if price_max is not None:
            query = query.filter(EcommerceItem.selling_price <= price_max)
        if in_stock is not None:
            query = query.join(
                CatalogProduct,
                CatalogProduct.id == EcommerceItem.catalog_product_id,
            )
            available = or_(
                CatalogProduct.track_quantity.is_(False),
                CatalogProduct.stock > 0,
            )
            # Only tracked products can actually be out of stock.
            query = query.filter(
                available
                if in_stock
                else and_(CatalogProduct.track_quantity.is_(True), CatalogProduct.stock <= 0),
            )
        if attribute_filters:
            for code, values in attribute_filters.items():
                cleaned = [v.strip() for v in values if v and v.strip()]
                if not cleaned:
                    continue
                # one filter code can belong to several profiles (Mouse / Keyboard / Wi-Fi all have "Connection"):
                # match the value on every filterable attribute of that code, not an arbitrary first one
                attrs_by_id = {
                    a.id: a
                    for a in self._db.query(CatalogAttribute)
                    .filter(CatalogAttribute.code == code, CatalogAttribute.is_filterable.is_(True))
                    .all()
                }
                if not attrs_by_id:
                    query = query.filter(EcommerceItem.catalog_product_id == "__none__")
                    continue
                matching_ids = {
                    row.product_id
                    for row in self._db.query(CatalogProductAttributeValue)
                    .filter(CatalogProductAttributeValue.attribute_id.in_(list(attrs_by_id)))
                    .all()
                    if self._value_matches_options(
                        row.value or "", cleaned, multi=attrs_by_id[row.attribute_id].field_type == "multi_select"
                    )
                }
                query = query.filter(
                    EcommerceItem.catalog_product_id.in_(matching_ids or ["__none__"]),
                )
        return query

    @staticmethod
    def _value_matches_options(stored: str, options: List[str], multi: bool = True) -> bool:
        if stored in options:
            return True
        if not multi:
            return False  # single-select: the whole value is the option ("USB" must not match "USB, Wi-Fi & LAN")
        parts = [p.strip() for p in stored.split(",") if p.strip()]
        return any(opt in parts for opt in options)

    def _apply_sort(self, query, sort: str):
        if sort == SORT_PRICE_ASC:
            return query.order_by(EcommerceItem.selling_price.asc(), EcommerceItem.slug)
        if sort == SORT_PRICE_DESC:
            return query.order_by(EcommerceItem.selling_price.desc(), EcommerceItem.slug)
        if sort == SORT_FEATURED:
            return query.order_by(
                desc(EcommerceItem.featured),
                EcommerceItem.sort_order,
                desc(EcommerceItem.updated_at),
            )
        if sort == SORT_BESTSELLING:
            sales = (
                self._db.query(
                    CommerceOrderItem.product_id.label("product_id"),
                    func.sum(CommerceOrderItem.quantity).label("qty"),
                )
                .group_by(CommerceOrderItem.product_id)
                .subquery()
            )
            return query.outerjoin(
                sales,
                sales.c.product_id == EcommerceItem.catalog_product_id,
            ).order_by(desc(func.coalesce(sales.c.qty, 0)), desc(EcommerceItem.updated_at))
        return query.order_by(desc(EcommerceItem.updated_at), EcommerceItem.slug)

    def list_products(
        self,
        *,
        page: int = 1,
        per_page: int = 48,
        search: Optional[str] = None,
        category_id: Optional[str] = None,
        category_slug: Optional[str] = None,
        brand_id: Optional[str] = None,
        brand_slug: Optional[str] = None,
        brand_slugs: Optional[List[str]] = None,
        featured: Optional[bool] = None,
        on_sale: Optional[bool] = None,
        price_min: Optional[Decimal] = None,
        price_max: Optional[Decimal] = None,
        in_stock: Optional[bool] = None,
        attribute_filters: Optional[Dict[str, List[str]]] = None,
        sort: str = SORT_NEWEST,
    ) -> StorefrontListResult:
        query = self._apply_filters(
            self._base_query(),
            search=search,
            category_id=category_id,
            category_slug=category_slug,
            brand_id=brand_id,
            brand_slug=brand_slug,
            brand_slugs=brand_slugs,
            featured=featured,
            on_sale=on_sale,
            price_min=price_min,
            price_max=price_max,
            in_stock=in_stock,
            attribute_filters=attribute_filters,
        )
        total = query.count()
        if search:
            # Relevance first; the chosen sort orders products that match equally well.
            query = query.order_by(desc(_search_rank(search)))
        rows = (
            self._apply_sort(query, sort)
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        self._items.preload_for_items(rows)
        views = [v for ec in rows if (v := self._items.resolve_storefront_from_ecommerce(ec))]
        return StorefrontListResult(items=views, total=total)

    def get_by_slug(self, slug: str) -> Optional[StorefrontProductView]:
        ec = (
            self._base_query()
            .filter(EcommerceItem.slug == slug)
            .first()
        )
        if not ec:
            return None
        view = self._items.resolve_storefront_from_ecommerce(ec, allow_preview=self._include_private)
        if not view or view.slug != slug:
            return None
        return view

    def get_ec_by_slug(self, slug: str) -> Optional[EcommerceItem]:
        return self._base_query().filter(EcommerceItem.slug == slug).first()

    def featured(self, *, limit: int = 12) -> List[StorefrontProductView]:
        result = self.list_products(featured=True, sort=SORT_FEATURED, per_page=limit, page=1)
        if result.items:
            return result.items
        return self.list_products(sort=SORT_FEATURED, per_page=limit, page=1).items

    def newest(self, *, limit: int = 12) -> List[StorefrontProductView]:
        return self.list_products(sort=SORT_NEWEST, per_page=limit, page=1).items

    def bestsellers(self, *, limit: int = 12) -> List[StorefrontProductView]:
        return self.list_products(sort=SORT_BESTSELLING, per_page=limit, page=1).items

    def _category_branch_ids(self, category_id: str) -> List[str]:
        """The category plus every category below it."""
        cat = self._db.get(CatalogCategory, category_id)
        if cat is None:
            return [category_id]
        if cat.path:
            rows = (
                self._db.query(CatalogCategory.id)
                .filter(CatalogCategory.path.like(f"{cat.path}%"))
                .all()
            )
            return [r[0] for r in rows] or [category_id]

        # Older rows may predate materialised paths — walk parent links instead.
        ids = [category_id]
        frontier = [category_id]
        while frontier:
            rows = (
                self._db.query(CatalogCategory.id)
                .filter(CatalogCategory.parent_id.in_(frontier))
                .all()
            )
            frontier = [r[0] for r in rows if r[0] not in ids]
            ids.extend(frontier)
        return ids

    def _category_related_ids(self, category_id: Optional[str]) -> List[str]:
        """Same category + siblings + descendants under the same parent (IT-shop related)."""
        if not category_id:
            return []
        cat = self._db.get(CatalogCategory, category_id)
        if not cat:
            return [category_id]

        ids: List[str] = [cat.id]

        # Siblings (same parent) — e.g. Keyboard ↔ Mouse under Accessories
        if cat.parent_id:
            sibling_ids = [
                row.id
                for row in self._db.query(CatalogCategory.id)
                .filter(
                    CatalogCategory.parent_id == cat.parent_id,
                    CatalogCategory.is_active.is_(True),
                    CatalogCategory.id != cat.id,
                )
                .all()
            ]
            ids.extend(sibling_ids)
            parent = self._db.get(CatalogCategory, cat.parent_id)
            if parent:
                ids.append(parent.id)
                # Cousins under the same grandparent when still sparse (Laptop → Gaming Laptop)
                if parent.parent_id:
                    cousin_ids = [
                        row.id
                        for row in self._db.query(CatalogCategory.id)
                        .filter(
                            CatalogCategory.parent_id == parent.parent_id,
                            CatalogCategory.is_active.is_(True),
                        )
                        .all()
                    ]
                    ids.extend(cousin_ids)
        else:
            # Top-level: include direct children (Laptop → All Laptop / Gaming Laptop)
            child_ids = [
                row.id
                for row in self._db.query(CatalogCategory.id)
                .filter(
                    CatalogCategory.parent_id == cat.id,
                    CatalogCategory.is_active.is_(True),
                )
                .all()
            ]
            ids.extend(child_ids)

        # De-dupe, keep order
        seen: set[str] = set()
        ordered: List[str] = []
        for cid in ids:
            if cid not in seen:
                seen.add(cid)
                ordered.append(cid)
        return ordered

    def _ordered_product_ids_in_category(self, category_id: str, exclude_item_id: str) -> List[str]:
        """Products in this category that customers have actually ordered, most
        ordered first. This is the "chosen by customers like you" signal — it is
        catalog-wide popularity, not the viewer's own history, since the shop is
        browsed signed-out most of the time."""
        rows = (
            self._db.query(
                CommerceOrderItem.product_id,
                func.count(CommerceOrderItem.id).label("times"),
            )
            .join(CatalogProduct, CatalogProduct.id == CommerceOrderItem.product_id)
            .join(EcommerceItem, EcommerceItem.catalog_product_id == CatalogProduct.id)
            .filter(
                EcommerceItem.primary_category_id == category_id,
                EcommerceItem.item_id != exclude_item_id,
            )
            .group_by(CommerceOrderItem.product_id)
            .order_by(desc("times"))
            .all()
        )
        return [row.product_id for row in rows]

    def more_to_love(self, slug: str, *, limit: int = 6) -> List[StorefrontProductView]:
        """Similar products for the product page's "More to love" row.

        Same category first — the ones customers have ordered ahead of the rest —
        then the remaining products of that category, and only if the category is
        too thin does it widen to the same brand.
        """
        ec = self.get_ec_by_slug(slug)
        if not ec or limit <= 0:
            return []

        collected: List[StorefrontProductView] = []
        seen: set[str] = {ec.item_id}

        def _append(rows: List[EcommerceItem]) -> None:
            self._items.preload_for_items(rows)
            for row in rows:
                if len(collected) >= limit:
                    return
                if row.item_id in seen:
                    continue
                view = self._items.resolve_storefront_from_ecommerce(row)
                if not view:
                    continue
                seen.add(row.item_id)
                collected.append(view)

        # _base_query already drops anything not live on the shop, so a product
        # that has since been Disabled or Archived cannot come back through the
        # order history.
        base = self._base_query().filter(EcommerceItem.item_id != ec.item_id)
        order = (desc(EcommerceItem.featured), desc(EcommerceItem.updated_at))

        if ec.primary_category_id:
            ordered_ids = self._ordered_product_ids_in_category(
                ec.primary_category_id, ec.item_id
            )
            if ordered_ids:
                rows = base.filter(EcommerceItem.catalog_product_id.in_(ordered_ids)).all()
                rank = {pid: idx for idx, pid in enumerate(ordered_ids)}
                rows.sort(key=lambda r: rank.get(r.catalog_product_id, len(rank)))
                _append(rows)

            if len(collected) < limit:
                _append(
                    base.filter(EcommerceItem.primary_category_id == ec.primary_category_id)
                    .order_by(*order)
                    .limit(limit * 2)
                    .all(),
                )

        if len(collected) < limit and ec.brand_id:
            _append(
                base.filter(EcommerceItem.brand_id == ec.brand_id)
                .order_by(*order)
                .limit(limit * 2)
                .all(),
            )

        return collected[:limit]

    def paired(self, slug: str, *, limit: int = 8) -> List[StorefrontProductView]:
        """Manually chosen pairs from the product form. Empty means the shop
        falls back to auto-picked related products under a different heading."""
        ec = self.get_ec_by_slug(slug)
        if not ec or not ec.catalog_product_id:
            return []
        ids = list_related_ids(self._db, ec.catalog_product_id)
        if not ids:
            return []
        rows = (
            self._base_query()
            .filter(EcommerceItem.catalog_product_id.in_(ids))
            .all()
        )
        rank = {pid: idx for idx, pid in enumerate(ids)}
        rows.sort(key=lambda r: rank.get(r.catalog_product_id, len(rank)))
        limited = rows[:limit]
        self._items.preload_for_items(limited)
        out: List[StorefrontProductView] = []
        for row in limited:
            view = self._items.resolve_storefront_from_ecommerce(row)
            if view:
                out.append(view)
        return out

    def related(self, slug: str, *, limit: int = 8) -> List[StorefrontProductView]:
        """Auto-related products: same category tree → same brand in-tree (no random global fill)."""
        ec = self.get_ec_by_slug(slug)
        if not ec:
            return []

        collected: List[StorefrontProductView] = []
        seen: set[str] = {ec.item_id}

        def _append(rows: List[EcommerceItem]) -> None:
            self._items.preload_for_items(rows)
            for row in rows:
                if row.item_id in seen:
                    continue
                view = self._items.resolve_storefront_from_ecommerce(row)
                if not view:
                    continue
                seen.add(row.item_id)
                collected.append(view)
                if len(collected) >= limit:
                    return

        base = self._base_query().filter(EcommerceItem.item_id != ec.item_id)
        order = (desc(EcommerceItem.featured), desc(EcommerceItem.updated_at))
        related_cat_ids = self._category_related_ids(ec.primary_category_id)

        # 1) Exact same category
        if ec.primary_category_id:
            _append(
                base.filter(EcommerceItem.primary_category_id == ec.primary_category_id)
                .order_by(*order)
                .limit(limit)
                .all(),
            )

        # 2) Sibling / parent / cousin categories in the same IT branch
        if len(collected) < limit and related_cat_ids:
            _append(
                base.filter(EcommerceItem.primary_category_id.in_(related_cat_ids))
                .order_by(*order)
                .limit(limit)
                .all(),
            )

        # 3) Same brand, but only inside the related category tree (avoid Brand PC next to earbuds)
        if len(collected) < limit and ec.brand_id and related_cat_ids:
            _append(
                base.filter(
                    EcommerceItem.brand_id == ec.brand_id,
                    EcommerceItem.primary_category_id.in_(related_cat_ids),
                )
                .order_by(*order)
                .limit(limit)
                .all(),
            )

        return collected[:limit]

    def facets(
        self,
        *,
        category_id: Optional[str] = None,
        category_slug: Optional[str] = None,
        search: Optional[str] = None,
        brand_slugs: Optional[List[str]] = None,
        price_min_filter: Optional[Decimal] = None,
        price_max_filter: Optional[Decimal] = None,
        in_stock: Optional[bool] = None,
        attribute_filters: Optional[Dict[str, List[str]]] = None,
    ) -> Dict:
        """Brand list, price bounds, and filterable attribute options (category-scoped).

        Counts narrow with the active filters. A group never constrains itself, so
        the shopper can still see the other options inside the group they just used.
        """

        # Resolved once so the attribute-profile category scoping below (which
        # category is actually being browsed) and the product query (which
        # matches the whole branch under it) agree on the same category.
        resolved_category_id = category_id
        if category_slug and not resolved_category_id:
            from sqlalchemy import case

            cat = (
                self._db.query(CatalogCategory)
                .filter(CatalogCategory.slug == category_slug)
                .order_by(
                    case((CatalogCategory.channel == "catalog", 0), else_=1),
                    CatalogCategory.sort_order.asc(),
                )
                .first()
            )
            if cat:
                resolved_category_id = cat.id

        def scoped(
            *,
            skip_brands: bool = False,
            skip_price: bool = False,
            skip_attr_code: Optional[str] = None,
        ):
            attrs = dict(attribute_filters or {})
            if skip_attr_code:
                attrs.pop(skip_attr_code, None)
            return self._apply_filters(
                self._base_query(),
                search=search,
                category_id=category_id,
                category_slug=category_slug,
                brand_slugs=None if skip_brands else brand_slugs,
                price_min=None if skip_price else price_min_filter,
                price_max=None if skip_price else price_max_filter,
                in_stock=in_stock,
                attribute_filters=attrs,
            )

        price_min, price_max = (
            scoped(skip_price=True)
            .with_entities(
                func.min(EcommerceItem.selling_price),
                func.max(EcommerceItem.selling_price),
            )
            .first()
            or (None, None)
        )

        brand_query = scoped(skip_brands=True)
        brand_counts = dict(
            brand_query.with_entities(EcommerceItem.brand_id, func.count(EcommerceItem.item_id))
            .filter(EcommerceItem.brand_id.isnot(None))
            .group_by(EcommerceItem.brand_id)
            .all(),
        )
        brands = []
        if brand_counts:
            for brand in self._db.query(CatalogBrand).filter(CatalogBrand.id.in_(brand_counts.keys())).all():
                brands.append(
                    {
                        "id": brand.id,
                        "slug": brand.slug,
                        "name": brand.name,
                        "count": brand_counts.get(brand.id, 0),
                    },
                )
            brands.sort(key=lambda b: b["name"])

        def product_ids_for(attr_code: str) -> List[str]:
            return [
                pid
                for (pid,) in scoped(skip_attr_code=attr_code)
                .with_entities(EcommerceItem.catalog_product_id)
                .filter(EcommerceItem.catalog_product_id.isnot(None))
                .distinct()
                .all()
                if pid
            ]

        attributes = self._attribute_facets(product_ids_for, resolved_category_id)

        return {
            "brands": brands,
            "price_min": price_min if price_min is not None else Decimal("0"),
            "price_max": price_max if price_max is not None else Decimal("0"),
            "attributes": attributes,
        }

    def _attribute_facets(
        self,
        product_ids_for: Callable[[str], List[str]],
        category_id: Optional[str] = None,
    ) -> List[dict]:
        configured = (
            self._db.query(CatalogFilter)
            .filter(
                CatalogFilter.source == "attribute",
                CatalogFilter.attribute_id.isnot(None),
            )
            .order_by(CatalogFilter.sort_order.asc(), CatalogFilter.name.asc())
            .all()
        )
        # attribute_id → (visible, sort_order). Missing config ⇒ use attribute storefront flag.
        filter_cfg: Dict[str, Tuple[bool, int]] = {}
        for row in configured:
            if not row.attribute_id:
                continue
            visible = bool(row.is_active and row.storefront_visible)
            filter_cfg[row.attribute_id] = (visible, int(row.sort_order or 0))

        attrs = (
            self._db.query(CatalogAttribute)
            .filter(
                CatalogAttribute.is_filterable.is_(True),
                CatalogAttribute.is_active.is_(True),
            )
            .order_by(CatalogAttribute.sort_order.asc(), CatalogAttribute.name.asc())
            .all()
        )
        attrs = [
            a
            for a in attrs
            if filter_cfg.get(
                a.id,
                (bool(getattr(a, "storefront_filter_visible", True)), a.sort_order or 0),
            )[0]
        ]
        attrs.sort(
            key=lambda a: (
                filter_cfg.get(
                    a.id,
                    (True, 10_000 + (a.sort_order or 0)),
                )[1],
                a.name,
            ),
        )

        # Category-scope by attribute profile: a profile with no configured
        # categories is unscoped (shown everywhere, same as before). Once an
        # admin picks categories for a profile (e.g. "Processor Specs" →
        # "Processor" only), its attributes only appear while browsing one of
        # those exact categories — so they no longer leak into a broader
        # parent category that also holds a sibling type (e.g. "Component",
        # which also contains "Casing" products).
        if category_id and attrs:
            group_ids = {a.group_id for a in attrs}
            profile_by_group: Dict[str, str] = dict(
                self._db.query(CatalogAttributeGroup.id, CatalogAttributeGroup.profile_id)
                .filter(CatalogAttributeGroup.id.in_(group_ids))
                .all(),
            )
            profile_ids = set(profile_by_group.values())
            raw_categories_by_profile: Dict[str, set] = {}
            if profile_ids:
                for pid, cid in (
                    self._db.query(
                        CatalogAttributeProfileCategory.profile_id,
                        CatalogAttributeProfileCategory.category_id,
                    )
                    .filter(CatalogAttributeProfileCategory.profile_id.in_(profile_ids))
                    .all()
                ):
                    raw_categories_by_profile.setdefault(pid, set()).add(cid)

            # Scoping a profile to a category also covers every category below
            # it — picking "Casing" applies to "Casing → Mid Tower" too, not
            # just the exact node an admin ticked.
            branch_cache: Dict[str, List[str]] = {}

            def _branch(cid: str) -> List[str]:
                if cid not in branch_cache:
                    branch_cache[cid] = self._category_branch_ids(cid)
                return branch_cache[cid]

            categories_by_profile: Dict[str, set] = {
                pid: {cid for raw in raw_ids for cid in _branch(raw)}
                for pid, raw_ids in raw_categories_by_profile.items()
            }

            def _profile_allows(attr: CatalogAttribute) -> bool:
                profile_id = profile_by_group.get(attr.group_id)
                scoped_categories = categories_by_profile.get(profile_id) if profile_id else None
                if not scoped_categories:
                    return True
                return category_id in scoped_categories

            attrs = [a for a in attrs if _profile_allows(a)]

        if not attrs:
            return []

        out: List[dict] = []
        for attr in attrs:
            # Each group is counted against the other groups' filters only.
            product_ids = product_ids_for(attr.code)
            seen: Dict[str, set] = {}
            if product_ids:
                value_rows = (
                    self._db.query(CatalogProductAttributeValue)
                    .filter(
                        CatalogProductAttributeValue.product_id.in_(product_ids),
                        CatalogProductAttributeValue.attribute_id == attr.id,
                    )
                    .all()
                )
                for row in value_rows:
                    raw = (row.value or "").strip()
                    if not raw:
                        continue
                    # only multi-select values are comma lists; a single-select value like "Print, Scan & Copy" is one option
                    parts = (
                        ([p.strip() for p in raw.split(",") if p.strip()] or [raw])
                        if attr.field_type == "multi_select"
                        else [raw]
                    )
                    for part in parts:
                        seen.setdefault(part, set()).add(row.product_id)

            predefined = parse_json_list(attr.predefined_values)
            ordered_values: List[str] = []
            for val in predefined:
                if val not in ordered_values:
                    ordered_values.append(val)
            for val in sorted(seen.keys()):
                if val not in ordered_values:
                    ordered_values.append(val)
            options = []
            for val in ordered_values:
                count = len(seen.get(val, set()))
                if count <= 0:
                    continue
                options.append(
                    {
                        "value": val,
                        "label": val.replace("_", " "),
                        "count": count,
                    },
                )
            display_type = getattr(attr, "filter_display_type", None) or "multi_select"
            # Prefer Catalog Filters display type when present (Filters page edits).
            cfg_row = next((r for r in configured if r.attribute_id == attr.id), None)
            if cfg_row and cfg_row.display_type:
                display_type = cfg_row.display_type
            if display_type == "boolean":
                # Always expose yes/no style options when boolean and any values exist.
                if not options and seen:
                    for val, pids in sorted(seen.items()):
                        options.append(
                            {
                                "value": val,
                                "label": val.replace("_", " "),
                                "count": len(pids),
                            },
                        )
            if not options and display_type not in ("range", "boolean"):
                continue
            if not options and display_type == "range":
                # Range still shown when numeric product values exist (options carry bounds).
                nums = []
                for val, pids in seen.items():
                    try:
                        nums.append((float("".join(ch for ch in val if ch.isdigit() or ch == ".")), len(pids)))
                    except ValueError:
                        continue
                if not nums:
                    continue
                lo = min(n for n, _ in nums)
                hi = max(n for n, _ in nums)
                options = [
                    {"value": str(lo), "label": "min", "count": sum(c for _, c in nums)},
                    {"value": str(hi), "label": "max", "count": sum(c for _, c in nums)},
                ]
            out.append(
                {
                    "id": attr.id,
                    "code": attr.code,
                    "name": attr.name,
                    "display_type": display_type,
                    "options": options,
                },
            )
        return out

    def filter_attributes_for_products(self, product_ids: List[str]) -> Dict[str, Dict[str, str]]:
        """Map catalog product id → { attribute_code: stored_value } for filterable attrs."""
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return {}
        rows = (
            self._db.query(CatalogProductAttributeValue, CatalogAttribute)
            .join(
                CatalogAttribute,
                CatalogAttribute.id == CatalogProductAttributeValue.attribute_id,
            )
            .filter(
                CatalogProductAttributeValue.product_id.in_(ids),
                CatalogAttribute.is_filterable.is_(True),
                CatalogAttribute.is_active.is_(True),
            )
            .all()
        )
        out: Dict[str, Dict[str, str]] = {}
        for pav, attr in rows:
            value = (pav.value or "").strip()
            if not value:
                continue
            out.setdefault(pav.product_id, {})[attr.code] = value
        return out

    def all_attributes_for_products(self, product_ids: List[str]) -> Dict[str, Dict[str, str]]:
        """All stored spec values, including non-filterable fields used by PC Builder."""
        ids = [pid for pid in product_ids if pid]
        if not ids:
            return {}
        rows = (
            self._db.query(CatalogProductAttributeValue, CatalogAttribute)
            .join(
                CatalogAttribute,
                CatalogAttribute.id == CatalogProductAttributeValue.attribute_id,
            )
            .filter(
                CatalogProductAttributeValue.product_id.in_(ids),
                CatalogAttribute.is_active.is_(True),
            )
            .all()
        )
        out: Dict[str, Dict[str, str]] = {}
        for pav, attr in rows:
            value = (pav.value or "").strip()
            if not value:
                continue
            code = (attr.code or "").strip() or (attr.name or "").strip().lower().replace(" ", "_")
            if code:
                out.setdefault(pav.product_id, {})[code] = value
            label = (attr.name or "").strip().lower()
            if label and label != code:
                out.setdefault(pav.product_id, {})[label.replace(" ", "_")] = value
        return out

    def list_categories(self, channel: str = "dropshipping") -> List[dict]:
        """Active category tree for storefront nav (roots + children).

        channel: ``catalog`` (admin Catalog → Categories) or ``dropshipping``
        (frontstore / China tree). Live Edit Auto menu uses ``catalog``.
        """
        channel_key = channel if channel in ("catalog", "dropshipping") else "dropshipping"
        rows = (
            self._db.query(CatalogCategory)
            .filter(
                CatalogCategory.is_active.is_(True),
                CatalogCategory.channel == channel_key,
            )
            .order_by(CatalogCategory.sort_order.asc(), CatalogCategory.name.asc())
            .all()
        )
        by_parent: Dict[Optional[str], List[CatalogCategory]] = {}
        for row in rows:
            by_parent.setdefault(row.parent_id, []).append(row)

        def node(row: CatalogCategory) -> dict:
            children = [node(child) for child in by_parent.get(row.id, [])]
            return {
                "id": row.id,
                "slug": row.slug,
                "name": row.name,
                "parent_id": row.parent_id,
                "icon_url": row.icon_url,
                "banner_url": row.banner_url,
                "show_in_top_menu": row.show_in_top_menu,
                "china_search_keyword": row.china_search_keyword,
                "children": children,
            }

        return [node(row) for row in by_parent.get(None, [])]

    def list_brands(self) -> List[dict]:
        """Active brands for storefront brand strip / nav.

        Every active brand, whatever its channel. Brands from an older import carry the
        dropshipping tag; preferring the catalog channel made the list collapse to a single
        brand as soon as one brand was created in the catalog.
        """
        rows = (
            self._db.query(CatalogBrand)
            .filter(CatalogBrand.is_active.is_(True))
            .order_by(CatalogBrand.sort_order.asc(), CatalogBrand.name.asc())
            .all()
        )
        return [
            {
                "id": row.id,
                "slug": row.slug,
                "name": row.name,
                "logo_url": row.logo_url,
            }
            for row in rows
        ]

    def resolve_slug(self, slug: str) -> Optional[dict]:
        """Resolve flat URL slug to entity type for Next.js routing."""
        normalized = slug.strip().lower()
        if not normalized:
            return None

        # Legacy / demo menu slugs → current catalog_categories.slug values
        category_aliases = {
            "laptop-notebook": "laptop",
            "desktops": "desktop",
            "desktop-pc": "desktop",
            "component": "pc-component",
            "components": "pc-component",
            "accessories": "pc-accessory",
            "pc-accessories": "pc-accessory",
            "tablet": "tablet-pc",
            "tablets": "tablet-pc",
            "networking": "network",
            "security": "security-system",
            "gadget": "it-gadget",
            "gadgets": "it-gadget",
            "printer": "office",
            "printers": "office",
        }
        # Only remap legacy demo slugs when this storefront does not already
        # have a live category with that slug (the storefront uses /desktops, /component).
        category_lookup = normalized
        aliased = category_aliases.get(normalized)
        if aliased and aliased != normalized:
            existing = (
                self._db.query(CatalogCategory.id)
                .filter(
                    CatalogCategory.slug == normalized,
                    CatalogCategory.is_active.is_(True),
                )
                .first()
            )
            if existing is None:
                category_lookup = aliased

        product = self.get_by_slug(normalized)
        if product:
            ec = self.get_ec_by_slug(normalized)
            return {
                "type": "product",
                "slug": normalized,
                "product": product,
                "seo_title": ec.seo_title if ec else None,
                "seo_description": ec.seo_description if ec else None,
            }

        from sqlalchemy import case

        # Prefer catalog channel (admin Catalog → Categories / menu) over dropshipping
        # when the same slug exists in both. Brand is last so /msi opens the MSI category.
        category = (
            self._db.query(CatalogCategory)
            .filter(
                CatalogCategory.slug == category_lookup,
                CatalogCategory.is_active.is_(True),
            )
            .order_by(
                case((CatalogCategory.channel == "catalog", 0), else_=1),
                CatalogCategory.sort_order.asc(),
            )
            .first()
        )
        if category:
            return {
                "type": "category",
                "slug": category.slug,
                "category": {
                    "id": category.id,
                    "slug": category.slug,
                    "name": category.name,
                    "description": category.description,
                    "meta_title": category.meta_title,
                    "meta_description": category.meta_description,
                    "china_search_keyword": getattr(category, "china_search_keyword", None),
                    "parent_id": category.parent_id,
                    "show_price_comparison": bool(
                        getattr(category, "show_price_comparison", True)
                    ),
                },
            }

        brand = (
            self._db.query(CatalogBrand)
            .filter(CatalogBrand.slug == normalized, CatalogBrand.is_active.is_(True))
            .first()
        )
        if brand:
            return {
                "type": "brand",
                "slug": normalized,
                "brand": {
                    "id": brand.id,
                    "slug": brand.slug,
                    "name": brand.name,
                    "description": brand.description,
                    "meta_title": brand.meta_title,
                    "meta_description": brand.meta_description,
                    "logo_url": brand.logo_url,
                },
            }

        return None
