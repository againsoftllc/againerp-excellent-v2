"""Storefront product catalog API — ecommerce_items only (STEP 04)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_optional_user
from app.models.auth_user import AuthUser
from app.deps.storefront_customer_auth import (
    CustomerAuthContext,
    get_optional_storefront_customer,
)
from app.models.catalog_attribute import CatalogAttribute
from app.models.catalog_attribute_group import CatalogAttributeGroup
from app.models.catalog_category import CatalogCategory
from app.models.catalog_product import CatalogProduct
from app.models.product_page_banner import ProductPageBanner
from app.models.catalog_product_special import (
    BD_UTC_OFFSET_HOURS,
    CatalogProductSpecial,
    resolve_active_special,
)
from app.services.ecommerce.ecommerce_item_service import stock_status_flags
from app.models.catalog_product_attribute_value import CatalogProductAttributeValue
from app.models.catalog_product_review import CatalogProductReview
from app.models.catalog_product_qa import CatalogProductQa
from app.models.catalog_product_variant import CatalogProductVariant
from app.models.ecommerce_item import EcommerceItem
from app.models.ecommerce_item_category import EcommerceItemCategory
from app.models.website_settings import DEFAULT_WEBSITE_SETTINGS_ID, WebsiteSettings
from app.models.ecommerce_item_media import EcommerceItemMedia
from app.models.catalog_product_media import CatalogProductMedia
from app.models.media import Media
from app.schemas.catalog_product_review import parse_review_media
from app.services.brand_rewrite import rewrite_startech_to_againcart
from app.services.site_resolver import request_site_options
from app.services.storefront_site_options import commerce_option
from app.schemas.storefront import (
    StorefrontCategoryCrumbRead,
    StorefrontFacetAttributeOptionRead,
    StorefrontFacetAttributeRead,
    StorefrontFacetBrandRead,
    StorefrontFacetsRead,
    StorefrontFacetsResponse,
    StorefrontPageBannerRead,
    StorefrontPriceTierRead,
    StorefrontProductDetailRead,
    StorefrontProductDetailResponse,
    StorefrontProductListMeta,
    StorefrontProductListResponse,
    StorefrontProductRead,
    StorefrontProductResponse,
    StorefrontQaCreate,
    StorefrontQaCreateResponse,
    StorefrontQaListMeta,
    StorefrontQaListResponse,
    StorefrontQaRead,
    StorefrontReviewCreate,
    StorefrontReviewCreateResponse,
    StorefrontReviewListMeta,
    StorefrontReviewListResponse,
    StorefrontReviewRead,
    StorefrontSellerInfoRead,
    StorefrontSpecGroupRead,
    StorefrontSpecItemRead,
    StorefrontVariantOptionRead,
    StorefrontVariantRead,
)
from app.services.ecommerce.storefront_catalog_service import (
    SORT_BESTSELLING,
    SORT_FEATURED,
    SORT_NEWEST,
    SORT_PRICE_ASC,
    SORT_PRICE_DESC,
    StorefrontCatalogService,
)

router = APIRouter(prefix="/products", tags=["storefront-products"])

STOREFRONT_CACHE = "public, max-age=60, s-maxage=120, stale-while-revalidate=300"
STOREFRONT_NO_CACHE = "private, no-store, max-age=0, must-revalidate"

SORT_ALIASES = {
    "relevance": SORT_NEWEST,
    "newest": SORT_NEWEST,
    "price_asc": SORT_PRICE_ASC,
    "price_desc": SORT_PRICE_DESC,
    "best_selling": SORT_BESTSELLING,
    "bestselling": SORT_BESTSELLING,
    "featured": SORT_FEATURED,
}


def _set_cache(response: Response, *, private: bool = False) -> None:
    if private:
        # Staff preview shows Private products — never let a CDN or the
        # browser share that response with an anonymous visitor.
        response.headers["Cache-Control"] = "private, no-store"
        return

    response.headers["Cache-Control"] = STOREFRONT_CACHE


def _set_no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = STOREFRONT_NO_CACHE
    response.headers["Pragma"] = "no-cache"


def _view_to_read(
    view,
    *,
    rating: Optional[float] = None,
    review_count: Optional[int] = None,
    filter_attributes: Optional[dict[str, str]] = None,
) -> StorefrontProductRead:
    return StorefrontProductRead(
        id=view.id,
        item_id=view.item_id,
        slug=view.slug,
        name=view.name,
        price=view.price,
        compare_at_price=view.compare_at_price,
        stock=view.stock,
        track_quantity=view.track_quantity,
        stock_status=view.stock_status,
        brand=view.brand,
        category=view.category,
        category_slug=getattr(view, "category_slug", "") or "",
        thumbnail=view.thumbnail,
        in_stock=view.in_stock,
        availability_label=_availability_label(view),
        availability_color=_availability_color(view),
        sellable=_availability_sellable(view),
        contact_phone=_availability_contact_phone(view),
        short_description=rewrite_startech_to_againcart(view.short_description),
        featured=view.featured,
        sku=getattr(view, "sku", None),
        model=getattr(view, "model", None),
        rating=rating,
        review_count=review_count,
        filter_attributes=filter_attributes or {},
        has_options=bool(getattr(view, "has_options", False)),
    )


def _is_staff_preview(user) -> bool:
    """A signed-in ERP user may preview Private products on the shop.
    Customers and anonymous visitors never can."""
    return user is not None and getattr(user, "is_active", False)


def _availability_row(view):
    """The client-configured stock status row for this product, if any."""
    code = (getattr(view, "stock_status", None) or "").strip().lower()
    return stock_status_flags(code) if code else None


def _availability_label(view) -> str:
    row = _availability_row(view)
    if row is not None:
        return (row.badge_label or row.label or "").strip() or ("In Stock" if view.in_stock else "Out of Stock")
    # Auto (based on quantity) — derive it from stock.
    return "In Stock" if view.in_stock else "Out of Stock"


def _availability_color(view) -> str:
    row = _availability_row(view)
    if row is not None and (row.badge_color or "").strip():
        return row.badge_color.strip()
    return "#00b87a" if view.in_stock else "#d92128"


def _availability_sellable(view) -> bool:
    row = _availability_row(view)
    if row is not None:
        return bool(row.sellable)
    return bool(view.in_stock)


def _availability_contact_phone(view) -> Optional[str]:
    """"Call for Price" number — the product's own, else its status' default."""
    own = (getattr(view, "contact_phone", None) or "").strip()
    if own:
        return own
    row = _availability_row(view)
    if row is not None and (row.contact_phone or "").strip():
        return row.contact_phone.strip()
    return None


def _review_to_read(row: CatalogProductReview) -> StorefrontReviewRead:
    media = parse_review_media(getattr(row, "media_json", None), row.customer_image_url)
    return StorefrontReviewRead(
        id=row.id,
        customer_name=row.customer_name,
        rating=int(row.rating or 0),
        title=row.title or "",
        body=row.body or "",
        created_at=row.created_at,
        is_verified_purchase=bool(row.is_verified_purchase),
        helpful_votes=int(row.helpful_votes or 0),
        media_urls=[item.url for item in media if item.url],
    )


def _aggregate_approved_reviews(
    db: Session,
    product_ids: list[str],
) -> dict[str, tuple[float, int]]:
    """Map catalog product id → (average_rating, review_count) for approved reviews."""
    ids = [pid for pid in product_ids if pid]
    if not ids:
        return {}
    rows = (
        db.query(
            CatalogProductReview.product_id,
            func.avg(CatalogProductReview.rating),
            func.count(CatalogProductReview.id),
        )
        .filter(
            CatalogProductReview.product_id.in_(ids),
            CatalogProductReview.status == "approved",
        )
        .group_by(CatalogProductReview.product_id)
        .all()
    )
    out: dict[str, tuple[float, int]] = {}
    for product_id, avg_rating, count in rows:
        if not product_id or not count:
            continue
        out[str(product_id)] = (round(float(avg_rating), 2), int(count))
    return out


def _load_approved_reviews(
    db: Session,
    catalog_product_id: Optional[str],
    *,
    limit: int = 50,
) -> list[StorefrontReviewRead]:
    if not catalog_product_id:
        return []
    rows = (
        db.query(CatalogProductReview)
        .filter(
            CatalogProductReview.product_id == catalog_product_id,
            CatalogProductReview.status == "approved",
        )
        .order_by(CatalogProductReview.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_review_to_read(row) for row in rows]


def _qa_to_read(row: CatalogProductQa) -> StorefrontQaRead:
    return StorefrontQaRead(
        id=row.id,
        customer_name=row.customer_name,
        question=row.question,
        answer=row.answer,
        answered_by=row.answered_by,
        status=row.status,
        is_verified=bool(row.is_verified),
        created_at=row.created_at,
    )


def _load_public_qa(
    db: Session,
    catalog_product_id: Optional[str],
    *,
    limit: int = 50,
) -> list[StorefrontQaRead]:
    """Public Q&A: answered only (pending wait for admin reply — same as reviews)."""
    if not catalog_product_id:
        return []
    rows = (
        db.query(CatalogProductQa)
        .filter(
            CatalogProductQa.product_id == catalog_product_id,
            CatalogProductQa.status == "answered",
        )
        .order_by(CatalogProductQa.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_qa_to_read(row) for row in rows]


def _attach_review_stats(
    db: Session,
    views: list,
) -> list[StorefrontProductRead]:
    aggregates = _aggregate_approved_reviews(db, [getattr(v, "id", None) for v in views])
    filter_map = StorefrontCatalogService(db).filter_attributes_for_products(
        [getattr(v, "id", "") for v in views],
    )
    out: list[StorefrontProductRead] = []
    for view in views:
        rating, count = aggregates.get(view.id, (None, None))
        out.append(
            _view_to_read(
                view,
                rating=rating,
                review_count=count,
                filter_attributes=filter_map.get(view.id, {}),
            ),
        )
    return out


def _parse_attribute_filters(attrs: Optional[List[str]]) -> Optional[Dict[str, List[str]]]:
    """Parse `attrs` query values shaped as `code:value` (repeatable)."""
    if not attrs:
        return None
    out: Dict[str, List[str]] = {}
    for raw in attrs:
        if not raw or ":" not in raw:
            continue
        code, value = raw.split(":", 1)
        code = code.strip()
        value = value.strip()
        if not code or not value:
            continue
        out.setdefault(code, []).append(value)
    return out or None


def _parse_url_list(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if not value:
            continue
        # Absolute URLs and API uploads, plus storefront-relative paths such as
        # `/images/products/x.webp` — those are served by the shop's own public
        # folder, and dropping them left seeded products with a one-image
        # gallery. `//host/path` is excluded: it is protocol-relative, not local.
        if value.startswith(("http://", "https://")) or (
            value.startswith("/") and not value.startswith("//")
        ):
            out.append(_public_media_url(value))
    return out


def _public_media_url(url: str) -> str:
    """Normalize local Absolute API upload URLs to relative /uploads for storefront proxy."""
    value = (url or "").strip()
    if not value:
        return value
    if value.startswith("/uploads/"):
        return value
    marker = "/uploads/"
    idx = value.find(marker)
    if idx >= 0:
        return value[idx:]
    return value


def _catalog_product_media_urls(db: Session, catalog_product_id: str) -> list[str]:
    rows = (
        db.query(Media)
        .join(CatalogProductMedia, CatalogProductMedia.media_id == Media.id)
        .filter(
            CatalogProductMedia.product_id == catalog_product_id,
            Media.media_type == "image",
        )
        .order_by(CatalogProductMedia.sort_order, CatalogProductMedia.created_at)
        .all()
    )
    return [_public_media_url(m.url) for m in rows if m.url]


def _load_gallery(
    db: Session,
    item_id: str,
    thumbnail: Optional[str] = None,
    *,
    catalog_product_id: Optional[str] = None,
) -> list[str]:
    # Prefer Media Library attachments from catalog product (admin gallery).
    if catalog_product_id:
        media_urls = _catalog_product_media_urls(db, catalog_product_id)
        if media_urls:
            return media_urls

        product = db.get(CatalogProduct, catalog_product_id)
        if product:
            urls = _parse_url_list(getattr(product, "gallery_json", None))
            if not urls and product.custom_specs_json:
                try:
                    specs = json.loads(product.custom_specs_json)
                    if isinstance(specs, dict) and isinstance(specs.get("images"), list):
                        urls = [
                            _public_media_url(u)
                            for u in specs["images"]
                            if isinstance(u, str)
                            and u.strip().startswith(("http://", "https://", "/uploads/"))
                        ]
                except json.JSONDecodeError:
                    urls = []
            if urls:
                return urls

    rows = (
        db.query(Media)
        .join(EcommerceItemMedia, EcommerceItemMedia.media_id == Media.id)
        .filter(
            EcommerceItemMedia.item_id == item_id,
            Media.media_type == "image",
        )
        .order_by(EcommerceItemMedia.sort_order)
        .all()
    )
    urls = [_public_media_url(m.url) for m in rows if m.url]
    if urls:
        return urls

    # Last resort: catalog/product thumbnail (may still be seed placeholder)
    if catalog_product_id:
        product = db.get(CatalogProduct, catalog_product_id)
        if product and product.thumbnail:
            return [_public_media_url(product.thumbnail)]

    return [_public_media_url(thumbnail)] if thumbnail else []


def _youtube_id(url: str) -> Optional[str]:
    value = (url or "").strip()
    if not value:
        return None
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        path_parts = [part for part in parsed.path.split("/") if part]
        if "youtu.be" in host:
            return path_parts[0] if path_parts else None
        if "img.youtube.com" in host:
            if "vi" in path_parts:
                idx = path_parts.index("vi")
                if idx + 1 < len(path_parts):
                    return path_parts[idx + 1]
            return None
        if "youtube.com" in host or "youtube-nocookie.com" in host:
            query_id = parse_qs(parsed.query).get("v", [None])[0]
            if query_id:
                return query_id
            for marker in ("embed", "shorts"):
                if marker in path_parts:
                    idx = path_parts.index(marker)
                    if idx + 1 < len(path_parts):
                        return path_parts[idx + 1]
    except ValueError:
        return None
    return None


def _playable_video_url(media: Media) -> Optional[str]:
    for candidate in (getattr(media, "source_url", None), media.url):
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        value = candidate.strip()
        youtube_id = _youtube_id(value)
        if youtube_id:
            return f"https://www.youtube.com/watch?v={youtube_id}"
        if "img.youtube.com" in value.lower():
            continue
        if value.startswith(("http://", "https://", "/uploads/")):
            return _public_media_url(value)
    return None


def _catalog_product_video_urls(db: Session, catalog_product_id: str) -> list[str]:
    rows = (
        db.query(Media)
        .join(CatalogProductMedia, CatalogProductMedia.media_id == Media.id)
        .filter(
            CatalogProductMedia.product_id == catalog_product_id,
            Media.media_type == "video",
        )
        .order_by(CatalogProductMedia.sort_order, CatalogProductMedia.created_at)
        .all()
    )
    urls: list[str] = []
    for media in rows:
        playable = _playable_video_url(media)
        if playable and playable not in urls:
            urls.append(playable)
    return urls


def _load_video_urls(db: Session, catalog_product_id: Optional[str]) -> list[str]:
    if not catalog_product_id:
        return []
    merged: list[str] = []
    for url in _catalog_product_video_urls(db, catalog_product_id):
        if url not in merged:
            merged.append(url)

    product = db.get(CatalogProduct, catalog_product_id)
    if not product:
        return merged

    for url in _parse_url_list(getattr(product, "video_urls_json", None)):
        if url not in merged:
            merged.append(url)
    if merged:
        return merged
    if product.custom_specs_json:
        try:
            specs = json.loads(product.custom_specs_json)
            if isinstance(specs, dict) and isinstance(specs.get("videos"), list):
                return [u for u in specs["videos"] if isinstance(u, str) and u.startswith("http")]
        except json.JSONDecodeError:
            pass
    return merged


def _load_price_tiers(db: Session, catalog_product_id: Optional[str]) -> list[StorefrontPriceTierRead]:
    """Quantity ladder from Elim price_range (BDT), if stored on catalog product."""
    if not catalog_product_id:
        return []
    product = db.get(CatalogProduct, catalog_product_id)
    if not product:
        return []

    def _parse_tiers(raw: Any) -> list[StorefrontPriceTierRead]:
        if not isinstance(raw, list):
            return []
        by_moq: dict[int, StorefrontPriceTierRead] = {}
        for row in raw:
            if not isinstance(row, dict):
                continue
            try:
                min_qty = int(row.get("min_qty") or row.get("moq") or 0)
                price = Decimal(str(row.get("price_bdt") or row.get("price") or 0))
            except Exception:
                continue
            if min_qty < 1 or price <= 0:
                continue
            by_moq[min_qty] = StorefrontPriceTierRead(min_qty=min_qty, price_bdt=price)
        tiers = [by_moq[k] for k in sorted(by_moq.keys())]
        return tiers if len(tiers) >= 2 else []

    raw: Any = None
    dropship_meta: dict[str, Any] = {}
    for blob in (getattr(product, "dropship_meta_json", None), product.custom_specs_json):
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if isinstance(data.get("dropship"), dict):
            dropship_meta = data["dropship"]
        elif data.get("source") == "elim":
            dropship_meta = data
        if isinstance(data.get("price_tiers"), list):
            raw = data["price_tiers"]
            break
        if isinstance(dropship_meta.get("price_tiers"), list):
            raw = dropship_meta["price_tiers"]
            break

    tiers = _parse_tiers(raw)
    if tiers:
        return tiers

    # Backfill from Elim when MOQ ladder was never stored (older cache).
    elim_id = dropship_meta.get("elim_id")
    platform = dropship_meta.get("platform") or "alibaba"
    if not elim_id:
        return []
    try:
        from app.services.elim_catalog_import import (
            _price_tiers_from_elim,
            default_pricing_from_settings,
        )
        from app.services.elim_client import find_product

        detail = find_product(product_id=str(elim_id), platform=platform, lang="en")
        pricing = default_pricing_from_settings()
        # Prefer rates persisted on the product when available.
        try:
            if dropship_meta.get("exchange_rate"):
                pricing["exchange_rate"] = Decimal(str(dropship_meta["exchange_rate"]))
            if dropship_meta.get("markup_percent") is not None:
                pricing["markup_percent"] = Decimal(str(dropship_meta["markup_percent"]))
            if dropship_meta.get("profit_bdt") is not None:
                pricing["profit_bdt"] = Decimal(str(dropship_meta["profit_bdt"]))
            if dropship_meta.get("server_charge_bdt") is not None:
                pricing["server_charge_bdt"] = Decimal(str(dropship_meta["server_charge_bdt"]))
        except Exception:
            pass
        fresh = _price_tiers_from_elim(
            detail,
            exchange_rate=pricing["exchange_rate"],
            markup_percent=pricing.get("markup_percent", Decimal("0")),
            profit_bdt=pricing["profit_bdt"],
            server_charge_bdt=pricing["server_charge_bdt"],
        )
        if not fresh:
            return []
        # Persist for next request
        dropship_meta = {**dropship_meta, "price_tiers": fresh}
        product.dropship_meta_json = json.dumps(dropship_meta, ensure_ascii=False)
        if product.custom_specs_json:
            try:
                specs = json.loads(product.custom_specs_json)
                if isinstance(specs, dict):
                    specs["price_tiers"] = fresh
                    if isinstance(specs.get("dropship"), dict):
                        specs["dropship"] = {**specs["dropship"], "price_tiers": fresh}
                    product.custom_specs_json = json.dumps(specs, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        db.add(product)
        db.commit()
        return _parse_tiers(fresh)
    except Exception:
        return []


def _load_specifications(db: Session, catalog_product_id: Optional[str]) -> list[StorefrontSpecGroupRead]:
    if not catalog_product_id:
        return []
    rows = (
        db.query(CatalogProductAttributeValue, CatalogAttribute, CatalogAttributeGroup)
        .join(CatalogAttribute, CatalogAttribute.id == CatalogProductAttributeValue.attribute_id)
        .join(CatalogAttributeGroup, CatalogAttributeGroup.id == CatalogAttribute.group_id)
        .filter(CatalogProductAttributeValue.product_id == catalog_product_id)
        .order_by(
            CatalogAttributeGroup.sort_order,
            CatalogAttribute.sort_order,
            CatalogProductAttributeValue.sort_order,
        )
        .all()
    )
    groups: dict[str, StorefrontSpecGroupRead] = {}
    order: list[str] = []
    for val, attr, group in rows:
        if not val.value or not val.value.strip():
            continue
        if group.name not in groups:
            groups[group.name] = StorefrontSpecGroupRead(name=group.name, specs=[])
            order.append(group.name)
        shown = (val.display_value or "").strip() or val.value
        groups[group.name].specs.append(StorefrontSpecItemRead(label=attr.name, value=shown))
    profile_specs = [groups[name] for name in order]
    if profile_specs:
        return profile_specs

    # Fallback: Elim / custom product-only specs stored in custom_specs_json
    product = db.get(CatalogProduct, catalog_product_id)
    if not product or not product.custom_specs_json:
        return []
    try:
        raw = json.loads(product.custom_specs_json)
    except json.JSONDecodeError:
        return []
    custom_groups = raw.get("customGroups") if isinstance(raw, dict) else None
    custom_attrs = raw.get("customAttrs") if isinstance(raw, dict) else None
    if not isinstance(custom_groups, list) or not isinstance(custom_attrs, list):
        return []
    out: list[StorefrontSpecGroupRead] = []
    for group in custom_groups:
        if not isinstance(group, dict):
            continue
        gid = group.get("id")
        gname = (group.get("name") or "Specifications").strip() or "Specifications"
        specs: list[StorefrontSpecItemRead] = []
        for attr in custom_attrs:
            if not isinstance(attr, dict) or attr.get("groupId") != gid:
                continue
            label = (attr.get("name") or "").strip()
            value = (attr.get("value") or "").strip()
            if label and value:
                specs.append(StorefrontSpecItemRead(label=label, value=value))
        if specs:
            out.append(StorefrontSpecGroupRead(name=gname, specs=specs))
    return out


def _parse_variant_options(raw: Optional[str]) -> list[StorefrontVariantOptionRead]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    out: list[StorefrontVariantOptionRead] = []
    if isinstance(data, dict):
        for name, value in data.items():
            n = str(name or "").strip()
            v = str(value or "").strip()
            if n and v:
                out.append(StorefrontVariantOptionRead(name=n, value=v))
        return out
    if not isinstance(data, list):
        return []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if not name or not value:
            continue
        img = item.get("img_url") or item.get("image_url")
        out.append(
            StorefrontVariantOptionRead(
                name=name,
                value=value,
                image_url=str(img) if isinstance(img, str) and img else None,
            )
        )
    return out


def _parse_variant_gallery(db: Session, row: CatalogProductVariant) -> list[str]:
    """Image URLs only — a variant's gallery_json can carry a video entry
    (e.g. a YouTube link saved alongside the photos), and unlike the
    product-level gallery (`_load_gallery`, which already filters to
    `Media.media_type == "image"`), this raw JSON blob has no type of its
    own, so each entry's linked Media row is checked directly."""
    urls: list[str] = []
    raw = getattr(row, "gallery_json", None)
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str) and item.strip():
                    url = item.strip()
                    if _youtube_id(url):
                        continue
                    urls.append(_public_media_url(url))
                elif isinstance(item, dict):
                    url = str(item.get("url") or "").strip()
                    if not url:
                        continue
                    media_id = str(item.get("id") or "").strip()
                    if media_id:
                        media = db.get(Media, media_id)
                        if media and media.media_type and media.media_type != "image":
                            continue
                    if _youtube_id(url):
                        continue
                    urls.append(_public_media_url(url))
    if not urls and row.image_url:
        urls.append(_public_media_url(row.image_url))
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _parse_variant_video_urls(db: Session, row: CatalogProductVariant) -> list[str]:
    """Video entries embedded in this variant's own gallery_json (the
    counterpart `_parse_variant_gallery` strips out of the photo list) — a
    video attached to this specific color/variant, not the whole product."""
    urls: list[str] = []
    raw = getattr(row, "gallery_json", None)
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            for item in data:
                url = None
                if isinstance(item, str):
                    url = item.strip()
                elif isinstance(item, dict):
                    url = str(item.get("url") or "").strip()
                    media_id = str(item.get("id") or "").strip()
                    if media_id:
                        media = db.get(Media, media_id)
                        if media and media.media_type and media.media_type != "video":
                            continue
                if not url:
                    continue
                youtube_id = _youtube_id(url)
                if not youtube_id:
                    continue
                playable = f"https://www.youtube.com/watch?v={youtube_id}"
                if playable not in urls:
                    urls.append(playable)
    return urls


def _next_daily_window_close(bd_now: datetime, start_hour: int, end_hour: int) -> datetime:
    """Dhaka-local naive timestamp when a nightly [start_hour, end_hour) window
    (we're confirmed to be inside it right now) next closes. Rolls to tomorrow
    when today's boundary has already passed (covers the end_hour == 24 case,
    where "24:00 today" is really "00:00 tomorrow")."""
    candidate = bd_now.replace(hour=end_hour % 24, minute=0, second=0, microsecond=0)
    if candidate <= bd_now:
        candidate += timedelta(days=1)
    return candidate


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Tag a naive (but actually-UTC) datetime as UTC before it reaches the
    API response. Without an explicit offset, a browser's `Date` parser
    reads the ISO string as LOCAL time — on a Bangladesh (UTC+6) client that
    silently shifts every countdown target 6 hours early."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _load_sale_ends_at(db: Session, catalog_product_id: Optional[str]) -> Optional[datetime]:
    """Live countdown target for the PDP: resolve which special (if any) is
    active right now, the same rule used for the price itself, so the
    countdown never goes stale between admin saves. For a nightly-windowed
    special (Happy Hour), count down to tonight's window close rather than
    the campaign's overall end date — a shopper cares "closes in 40 minutes",
    not "closes in 3 weeks"."""
    if not catalog_product_id:
        return None
    specials = (
        db.query(CatalogProductSpecial)
        .filter(CatalogProductSpecial.product_id == catalog_product_id)
        .all()
    )
    if specials:
        active = resolve_active_special(specials)
        if not active:
            return None
        if active.daily_start_hour is not None and active.daily_end_hour is not None:
            bd_now = datetime.utcnow() + timedelta(hours=BD_UTC_OFFSET_HOURS)
            window_close_bd = _next_daily_window_close(
                bd_now, active.daily_start_hour, active.daily_end_hour
            )
            window_close_utc = window_close_bd - timedelta(hours=BD_UTC_OFFSET_HOURS)
            if active.date_end and active.date_end < window_close_utc:
                return _as_utc(active.date_end)
            return _as_utc(window_close_utc)
        return _as_utc(active.date_end)

    # Legacy fallback for products with no catalog_product_specials rows at all.
    product = db.get(CatalogProduct, catalog_product_id)
    if not product:
        return None
    ends = getattr(product, "sale_ends_at", None)
    if isinstance(ends, datetime):
        return _as_utc(ends)
    if product.custom_specs_json:
        try:
            specs = json.loads(product.custom_specs_json)
            raw = specs.get("sale_ends_at") if isinstance(specs, dict) else None
            if isinstance(raw, str) and raw.strip():
                try:
                    return datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
                except ValueError:
                    return None
        except json.JSONDecodeError:
            return None
    return None


def _load_shipping_meta(db: Session, catalog_product_id: Optional[str]) -> tuple[Optional[float], dict[str, float]]:
    """Return (default_weight_kg, {external_sku_id: weight_kg}). Backfills from Elim when missing."""
    empty: tuple[Optional[float], dict[str, float]] = (None, {})
    if not catalog_product_id:
        return empty
    product = db.get(CatalogProduct, catalog_product_id)
    if not product:
        return empty

    dropship_meta: dict[str, Any] = {}
    shipping_by_sku: dict[str, Any] = {}
    weight_kg: Optional[float] = None

    for blob in (getattr(product, "dropship_meta_json", None), product.custom_specs_json):
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if isinstance(data.get("dropship"), dict):
            dropship_meta = data["dropship"]
        elif data.get("source") == "elim":
            dropship_meta = data
        if isinstance(data.get("shipping_by_sku"), dict):
            shipping_by_sku = data["shipping_by_sku"]
        elif isinstance(dropship_meta.get("shipping_by_sku"), dict):
            shipping_by_sku = dropship_meta["shipping_by_sku"]
        raw_w = data.get("weight_kg")
        if raw_w is None:
            raw_w = dropship_meta.get("weight_kg")
        if raw_w is not None:
            try:
                weight_kg = float(raw_w)
            except (TypeError, ValueError):
                weight_kg = None
        if shipping_by_sku:
            break

    def _map_weights(src: dict[str, Any]) -> dict[str, float]:
        out: dict[str, float] = {}
        for sku_id, row in src.items():
            if not isinstance(row, dict):
                continue
            try:
                w = float(row.get("weight_kg") or 0)
            except (TypeError, ValueError):
                w = 0.0
            if w <= 0 and row.get("weight_g"):
                try:
                    w = float(row["weight_g"]) / 1000.0
                except (TypeError, ValueError):
                    w = 0.0
            if w > 0:
                out[str(sku_id)] = round(w, 3)
        return out

    by_sku = _map_weights(shipping_by_sku)
    if by_sku or (weight_kg is not None and weight_kg > 0):
        if weight_kg is None or weight_kg <= 0:
            vals = sorted(by_sku.values())
            weight_kg = vals[len(vals) // 2] if vals else None
        return weight_kg, by_sku

    elim_id = dropship_meta.get("elim_id")
    platform = dropship_meta.get("platform") or "alibaba"
    if not elim_id:
        return empty
    try:
        from app.services.elim_catalog_import import (
            _default_weight_kg,
            _shipping_by_sku_from_elim,
        )
        from app.services.elim_client import find_product

        detail = find_product(product_id=str(elim_id), platform=platform, lang="en")
        fresh = _shipping_by_sku_from_elim(detail)
        fresh_default = _default_weight_kg(fresh)
        if not fresh:
            return empty
        dropship_meta = {
            **dropship_meta,
            "shipping_by_sku": fresh,
            "weight_kg": fresh_default,
        }
        product.dropship_meta_json = json.dumps(dropship_meta, ensure_ascii=False)
        if product.custom_specs_json:
            try:
                specs = json.loads(product.custom_specs_json)
                if isinstance(specs, dict):
                    specs["shipping_by_sku"] = fresh
                    specs["weight_kg"] = fresh_default
                    if isinstance(specs.get("dropship"), dict):
                        specs["dropship"] = {
                            **specs["dropship"],
                            "shipping_by_sku": fresh,
                            "weight_kg": fresh_default,
                        }
                    product.custom_specs_json = json.dumps(specs, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        db.add(product)
        db.commit()
        return fresh_default, _map_weights(fresh)
    except Exception:
        return empty


def _active_special_price(db: Session, catalog_product_id: Optional[str]) -> Optional[Decimal]:
    """Price of the special that is live right now, or None."""
    if not catalog_product_id:
        return None
    specials = (
        db.query(CatalogProductSpecial)
        .filter(CatalogProductSpecial.product_id == catalog_product_id)
        .all()
    )
    if not specials:
        return None
    active = resolve_active_special(specials)
    return Decimal(active.price) if active is not None else None


def _load_variants(
    db: Session,
    catalog_product_id: Optional[str],
    *,
    weight_by_sku: Optional[dict[str, float]] = None,
) -> list[StorefrontVariantRead]:
    if not catalog_product_id:
        return []
    weights = weight_by_sku if weight_by_sku is not None else _load_shipping_meta(db, catalog_product_id)[1]
    rows = (
        db.query(CatalogProductVariant)
        .filter(
            CatalogProductVariant.product_id == catalog_product_id,
            CatalogProductVariant.status == "published",
        )
        .order_by(CatalogProductVariant.sort_order.asc(), CatalogProductVariant.name.asc())
        .all()
    )
    _special = _active_special_price(db, catalog_product_id)
    _variant_delta = Decimal("0")
    if _special is not None and rows:
        _anchor = next(
            (Decimal(r.price or 0) for r in rows if r.is_default),
            Decimal(rows[0].price or 0),
        )
        # The default variant lands exactly on the special price; the others keep
        # whatever premium/discount they carry relative to it.
        _variant_delta = _special - _anchor
    out: list[StorefrontVariantRead] = []
    for row in rows:
        options = _parse_variant_options(row.options_json)
        # Skip bare default rows with no selectable options
        if not options and len(rows) == 1:
            continue
        ext = (row.external_sku_id or "").strip()
        weight_kg = weights.get(ext) if ext else None
        out.append(
            StorefrontVariantRead(
                id=row.id,
                sku=row.sku,
                name=row.name,
                price=max(Decimal(row.price or 0) + _variant_delta, Decimal("0")),
                stock=int(row.stock or 0),
                image_url=row.image_url,
                gallery=_parse_variant_gallery(db, row),
                video_urls=_parse_variant_video_urls(db, row),
                is_default=bool(row.is_default),
                options=options,
                weight_kg=weight_kg,
            )
        )
    return out


def _filter_specs_for_variants(
    specs: list[StorefrontSpecGroupRead],
    variants: list[StorefrontVariantRead],
) -> list[StorefrontSpecGroupRead]:
    """Drop Color/Size-style rows from specs when they are selectable variants."""
    axis_names = {
        opt.name.strip().lower()
        for v in variants
        for opt in v.options
        if opt.name.strip()
    }
    if not axis_names:
        return specs
    cleaned: list[StorefrontSpecGroupRead] = []
    for group in specs:
        items = [s for s in group.specs if s.label.strip().lower() not in axis_names]
        # Also collapse duplicate labels remaining into unique pairs
        seen: set[tuple[str, str]] = set()
        unique: list[StorefrontSpecItemRead] = []
        for s in items:
            key = (s.label.strip().lower(), s.value.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            unique.append(s)
        if unique:
            cleaned.append(StorefrontSpecGroupRead(name=group.name, specs=unique))
    return cleaned


def _load_seller_and_source(
    db: Session,
    catalog_product_id: Optional[str],
    specifications_json: Optional[str] = None,
) -> tuple[Optional[StorefrontSellerInfoRead], Optional[str]]:
    seller: Optional[dict[str, Any]] = None
    source_url: Optional[str] = None

    if catalog_product_id:
        product = db.get(CatalogProduct, catalog_product_id)
        if product:
            source_url = product.source_url
            if product.seller_info_json:
                try:
                    parsed = json.loads(product.seller_info_json)
                    if isinstance(parsed, dict):
                        seller = parsed
                except json.JSONDecodeError:
                    pass

    if seller is None and specifications_json:
        try:
            raw = json.loads(specifications_json)
            if isinstance(raw, dict):
                if isinstance(raw.get("seller"), dict):
                    seller = raw["seller"]
                if not source_url and isinstance(raw.get("source_url"), str):
                    source_url = raw["source_url"]
                dropship = raw.get("dropship")
                if not source_url and isinstance(dropship, dict) and isinstance(dropship.get("supplier_link"), str):
                    source_url = dropship["supplier_link"]
        except json.JSONDecodeError:
            pass

    if not seller:
        return None, source_url

    def _num(key: str) -> Optional[float]:
        val = seller.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    return (
        StorefrontSellerInfoRead(
            id=str(seller["id"]) if seller.get("id") is not None else None,
            name=str(seller["name"]) if seller.get("name") is not None else None,
            store_name=str(seller["store_name"]) if seller.get("store_name") is not None else None,
            level=_num("level"),
            delivery_score=_num("delivery_score"),
            item_score=_num("item_score"),
            service_score=_num("service_score"),
        ),
        source_url,
    )


def _load_sales_and_rating(
    db: Session,
    catalog_product_id: Optional[str],
    specifications_json: Optional[str],
    seller_info: Optional[StorefrontSellerInfoRead],
) -> tuple[Optional[int], Optional[float], Optional[int]]:
    """Sold count from dropship meta; rating/count prefer catalog_product_reviews."""
    sales_volume: Optional[int] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    dropship: Optional[dict[str, Any]] = None

    if catalog_product_id:
        aggregates = _aggregate_approved_reviews(db, [catalog_product_id])
        if catalog_product_id in aggregates:
            rating, review_count = aggregates[catalog_product_id]

    if catalog_product_id:
        product = db.get(CatalogProduct, catalog_product_id)
        if product and product.dropship_meta_json:
            try:
                parsed = json.loads(product.dropship_meta_json)
                if isinstance(parsed, dict):
                    dropship = parsed
            except json.JSONDecodeError:
                pass

    if dropship is None and specifications_json:
        try:
            raw = json.loads(specifications_json)
            if isinstance(raw, dict) and isinstance(raw.get("dropship"), dict):
                dropship = raw["dropship"]
        except json.JSONDecodeError:
            pass

    if dropship:
        raw_sales = dropship.get("sales_volume")
        if raw_sales is not None:
            try:
                if isinstance(raw_sales, (int, float)):
                    sales_volume = int(raw_sales)
                else:
                    text = str(raw_sales).replace(",", "").strip()
                    digits = "".join(ch for ch in text if ch.isdigit())
                    if digits:
                        sales_volume = int(digits)
            except (TypeError, ValueError):
                sales_volume = None

    # Fallback: Elim seller score when no approved catalog reviews yet
    if rating is None and seller_info and seller_info.item_score is not None:
        score = float(seller_info.item_score)
        rating = score if score <= 5 else round(score / 20, 1)

    return sales_volume, rating, review_count


def _load_page_banners(
    db: Session, category_id: Optional[str], product_id: Optional[str]
) -> list[StorefrontPageBannerRead]:
    """Active promo banners (e.g. "Free Home Delivery") that apply to this
    product — an "all" banner always matches; a "category" banner matches if
    the product's category is the targeted category or a descendant of it;
    a "product" banner matches only that exact product."""
    banners = (
        db.query(ProductPageBanner)
        .filter(ProductPageBanner.is_active.is_(True))
        .order_by(ProductPageBanner.sort_order.asc(), ProductPageBanner.created_at.asc())
        .all()
    )
    if not banners:
        return []

    product_category_path = None
    if category_id:
        cat = db.get(CatalogCategory, category_id)
        if cat:
            product_category_path = cat.path

    matched: list[ProductPageBanner] = []
    for banner in banners:
        if banner.target_type == "all":
            matched.append(banner)
        elif banner.target_type == "product" and product_id:
            ids = json.loads(banner.target_product_ids_json or "[]")
            if product_id in ids:
                matched.append(banner)
        elif banner.target_type == "category" and product_category_path:
            cat_ids = json.loads(banner.target_category_ids_json or "[]")
            if not cat_ids:
                continue
            targets = db.query(CatalogCategory).filter(CatalogCategory.id.in_(cat_ids)).all()
            if any(product_category_path.startswith(t.path) for t in targets if t.path):
                matched.append(banner)

    return [
        StorefrontPageBannerRead(
            id=b.id,
            image_url=b.image_url,
            link_href=b.link_href,
            alt_text=b.alt_text or b.name,
        )
        for b in matched
        if b.image_url
    ]


def _most_specific_category_id(
    db: Session,
    item_id: Optional[str],
    fallback_id: Optional[str],
) -> Optional[str]:
    """The deepest category actually assigned to this item.

    A product can carry several category tags (e.g. Component, Casing,
    Monarch), with only one flagged `is_primary` for admin purposes — that
    flag is "whichever the admin picked/clicked first", not necessarily the
    most specific one. The breadcrumb reads better built from whichever
    assignment sits deepest in the tree, ties broken toward the primary.
    """
    if not item_id:
        return fallback_id
    rows = (
        db.query(EcommerceItemCategory.category_id, CatalogCategory.depth, EcommerceItemCategory.is_primary)
        .join(CatalogCategory, CatalogCategory.id == EcommerceItemCategory.category_id)
        .filter(EcommerceItemCategory.item_id == item_id, CatalogCategory.is_active.is_(True))
        .all()
    )
    if not rows:
        return fallback_id
    best = max(rows, key=lambda r: (r[1], r[2]))
    return best[0]


def _load_category_ancestors(db: Session, category_id: Optional[str]) -> list[StorefrontCategoryCrumbRead]:
    """Full root-to-leaf chain for the product's most specific category, read
    off its materialized `path` (/id/id/.../own_id/) so the PDP breadcrumb
    shows the whole tree — Component > Casing > Monarch — not just one level."""
    if not category_id:
        return []
    cat = db.get(CatalogCategory, category_id)
    if not cat or not cat.path:
        return []
    chain_ids = [seg for seg in cat.path.split("/") if seg]
    if not chain_ids:
        return []
    rows = db.query(CatalogCategory).filter(CatalogCategory.id.in_(chain_ids)).all()
    by_id = {row.id: row for row in rows}
    return [
        StorefrontCategoryCrumbRead(name=row.name, slug=row.slug)
        for cid in chain_ids
        if (row := by_id.get(cid)) and row.is_active
    ]


def _load_warranty(db: Session, catalog_product_id: Optional[str]) -> Optional[str]:
    if not catalog_product_id:
        return None
    product = db.get(CatalogProduct, catalog_product_id)
    return ((product.warranty or "").strip() or None) if product else None


def _detail_from_ec(view, ec: EcommerceItem, db: Session) -> StorefrontProductDetailRead:
    base = _view_to_read(view)
    seller_info, source_url = _load_seller_and_source(
        db,
        ec.catalog_product_id,
        ec.specifications_json,
    )
    sales_volume, rating, review_count = _load_sales_and_rating(
        db,
        ec.catalog_product_id,
        ec.specifications_json,
        seller_info,
    )
    weight_kg, weight_by_sku = _load_shipping_meta(db, ec.catalog_product_id)
    variants = _load_variants(db, ec.catalog_product_id, weight_by_sku=weight_by_sku)
    specifications = _filter_specs_for_variants(
        _load_specifications(db, ec.catalog_product_id),
        variants,
    )
    reviews = _load_approved_reviews(db, ec.catalog_product_id)
    qa = _load_public_qa(db, ec.catalog_product_id)
    base_data = base.model_dump()
    base_data.pop("rating", None)
    base_data.pop("review_count", None)
    if base_data.get("short_description"):
        base_data["short_description"] = rewrite_startech_to_againcart(
            base_data.get("short_description")
        )

    return StorefrontProductDetailRead(
        **base_data,
        full_description=rewrite_startech_to_againcart(ec.full_description),
        seo_title=rewrite_startech_to_againcart(ec.seo_title),
        seo_description=rewrite_startech_to_againcart(ec.seo_description),
        warranty=_load_warranty(db, ec.catalog_product_id),
        brand_id=ec.brand_id,
        category_id=ec.primary_category_id,
        category_ancestors=_load_category_ancestors(
            db, _most_specific_category_id(db, ec.item_id, ec.primary_category_id)
        ),
        specifications=specifications,
        gallery=_load_gallery(
            db,
            ec.item_id,
            view.thumbnail,
            catalog_product_id=ec.catalog_product_id,
        ),
        video_urls=_load_video_urls(db, ec.catalog_product_id),
        seller_info=seller_info,
        source_url=source_url,
        variants=variants,
        sale_ends_at=_load_sale_ends_at(db, ec.catalog_product_id),
        sales_volume=sales_volume,
        rating=rating,
        review_count=review_count if review_count is not None else (len(reviews) or None),
        price_tiers=_load_price_tiers(db, ec.catalog_product_id),
        weight_kg=weight_kg,
        reviews=reviews,
        qa=qa,
        page_banners=_load_page_banners(db, ec.primary_category_id, ec.catalog_product_id),
    )


def _normalize_sort(sort: Optional[str]) -> str:
    if not sort:
        return SORT_NEWEST
    return SORT_ALIASES.get(sort.strip().lower(), SORT_NEWEST)


@router.get("", response_model=StorefrontProductListResponse)
def list_storefront_products(
    response: Response,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(48, ge=1, le=200),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None, description="Primary category id"),
    category_slug: Optional[str] = Query(None),
    brand: Optional[str] = Query(None, description="Brand id"),
    brand_slug: Optional[str] = Query(None),
    brands: Optional[List[str]] = Query(None, description="Multiple brand slugs (filter panel)"),
    featured: Optional[bool] = Query(None),
    on_sale: Optional[bool] = Query(None),
    price_min: Optional[Decimal] = Query(None, ge=0),
    price_max: Optional[Decimal] = Query(None, ge=0),
    in_stock: Optional[bool] = Query(None),
    attrs: Optional[List[str]] = Query(
        None,
        description="Attribute filters as code:value (repeatable), e.g. form_factor:mid_tower",
    ),
    sort: Optional[str] = Query(None),
) -> StorefrontProductListResponse:
    _set_cache(response)
    service = StorefrontCatalogService(db)
    result = service.list_products(
        page=page,
        per_page=per_page,
        search=search,
        category_id=category,
        category_slug=category_slug,
        brand_id=brand,
        brand_slug=brand_slug,
        brand_slugs=brands,
        featured=featured,
        on_sale=on_sale,
        price_min=price_min,
        price_max=price_max,
        in_stock=in_stock,
        attribute_filters=_parse_attribute_filters(attrs),
        sort=_normalize_sort(sort),
    )
    return StorefrontProductListResponse(
        data=_attach_review_stats(db, result.items),
        meta=StorefrontProductListMeta(count=result.total, page=page, per_page=per_page),
    )


@router.get("/featured", response_model=StorefrontProductListResponse)
def featured_products(
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(12, ge=1, le=48),
) -> StorefrontProductListResponse:
    _set_cache(response)
    items = StorefrontCatalogService(db).featured(limit=limit)
    return StorefrontProductListResponse(
        data=_attach_review_stats(db, items),
        meta=StorefrontProductListMeta(count=len(items), page=1, per_page=limit),
    )


@router.get("/newest", response_model=StorefrontProductListResponse)
def newest_products(
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(12, ge=1, le=48),
) -> StorefrontProductListResponse:
    _set_cache(response)
    items = StorefrontCatalogService(db).newest(limit=limit)
    return StorefrontProductListResponse(
        data=_attach_review_stats(db, items),
        meta=StorefrontProductListMeta(count=len(items), page=1, per_page=limit),
    )


@router.get("/bestsellers", response_model=StorefrontProductListResponse)
def bestseller_products(
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(12, ge=1, le=48),
) -> StorefrontProductListResponse:
    _set_cache(response)
    items = StorefrontCatalogService(db).bestsellers(limit=limit)
    return StorefrontProductListResponse(
        data=_attach_review_stats(db, items),
        meta=StorefrontProductListMeta(count=len(items), page=1, per_page=limit),
    )


@router.get("/facets", response_model=StorefrontFacetsResponse)
def storefront_product_facets(
    response: Response,
    db: Session = Depends(get_db),
    category: Optional[str] = Query(None, description="Primary category id"),
    category_slug: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    brands: Optional[List[str]] = Query(None, description="Active brand slug filters"),
    price_min: Optional[Decimal] = Query(None, ge=0),
    price_max: Optional[Decimal] = Query(None, ge=0),
    in_stock: Optional[bool] = Query(None),
    attrs: Optional[List[str]] = Query(
        None,
        description="Active attribute filters as code:value (repeatable)",
    ),
) -> StorefrontFacetsResponse:
    _set_cache(response)
    service = StorefrontCatalogService(db)
    result = service.facets(
        category_id=category,
        category_slug=category_slug,
        search=search,
        brand_slugs=brands,
        price_min_filter=price_min,
        price_max_filter=price_max,
        in_stock=in_stock,
        attribute_filters=_parse_attribute_filters(attrs),
    )
    return StorefrontFacetsResponse(
        data=StorefrontFacetsRead(
            brands=[StorefrontFacetBrandRead(**b) for b in result["brands"]],
            price_min=result["price_min"],
            price_max=result["price_max"],
            attributes=[
                StorefrontFacetAttributeRead(
                    id=attr["id"],
                    code=attr["code"],
                    name=attr["name"],
                    display_type=attr.get("display_type") or "multi_select",
                    options=[StorefrontFacetAttributeOptionRead(**opt) for opt in attr["options"]],
                )
                for attr in result.get("attributes", [])
            ],
        ),
    )


@router.get("/by-slug/{slug}/reviews", response_model=StorefrontReviewListResponse)
def list_storefront_product_reviews(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
) -> StorefrontReviewListResponse:
    """Public approved reviews for a storefront product (frontstore PDP)."""
    _set_no_cache(response)
    service = StorefrontCatalogService(db)
    ec = service.get_ec_by_slug(slug)
    if not ec:
        raise HTTPException(status_code=404, detail="Product not found")
    catalog_id = ec.catalog_product_id
    reviews = _load_approved_reviews(db, catalog_id, limit=limit)
    aggregates = _aggregate_approved_reviews(db, [catalog_id] if catalog_id else [])
    average, count = aggregates.get(catalog_id or "", (None, len(reviews)))
    return StorefrontReviewListResponse(
        data=reviews,
        meta=StorefrontReviewListMeta(
            count=count if count is not None else len(reviews),
            average_rating=average,
        ),
    )


def _next_storefront_review_number(db: Session) -> str:
    count = db.query(CatalogProductReview).count() + 1
    return f"R-{20000 + count}"


def _next_storefront_question_number(db: Session) -> str:
    count = db.query(CatalogProductQa).count() + 1
    return f"Q-{20000 + count}"


def _resolve_catalog_for_slug(db: Session, slug: str) -> tuple[EcommerceItem, CatalogProduct]:
    service = StorefrontCatalogService(db)
    ec = service.get_ec_by_slug(slug)
    if not ec or not ec.catalog_product_id:
        raise HTTPException(status_code=404, detail="Product not found")
    product = db.get(CatalogProduct, ec.catalog_product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ec, product


@router.post("/by-slug/{slug}/reviews", response_model=StorefrontReviewCreateResponse, status_code=201)
def create_storefront_product_review(
    slug: str,
    payload: StorefrontReviewCreate,
    http_request: Request,
    db: Session = Depends(get_db),
    ctx: Optional[CustomerAuthContext] = Depends(get_optional_storefront_customer),
) -> StorefrontReviewCreateResponse:
    """Shopper review → catalog_product_reviews (pending until admin approves)."""
    options = request_site_options(db, http_request)
    if not commerce_option(options, "allow_reviews"):
        raise HTTPException(status_code=403, detail="Reviews are turned off for this store")
    if ctx is None and not commerce_option(options, "allow_guest_reviews"):
        raise HTTPException(status_code=401, detail="Please sign in to write a review")

    _ec, product = _resolve_catalog_for_slug(db, slug)
    name = payload.customer_name.strip()
    body = payload.body.strip()
    title = (payload.title or "").strip() or (body[:80] + ("…" if len(body) > 80 else ""))
    customer_id = ctx[2].id if ctx else None
    if ctx and not name:
        name = ctx[2].name or "Customer"

    sentiment = "positive" if payload.rating >= 4 else "negative" if payload.rating <= 2 else "neutral"
    row = CatalogProductReview(
        id=str(uuid.uuid4()),
        review_number=_next_storefront_review_number(db),
        product_id=product.id,
        product_name=product.name,
        product_sku=product.sku or "",
        product_brand=product.brand,
        product_category=product.category,
        product_image_url=product.thumbnail,
        customer_id=customer_id,
        customer_name=name,
        review_type="text",
        status="pending",
        rating=payload.rating,
        title=title,
        body=body,
        sentiment=sentiment,
        is_verified_purchase=False,
        media_json="[]",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return StorefrontReviewCreateResponse(data=_review_to_read(row))


@router.get("/by-slug/{slug}/qa", response_model=StorefrontQaListResponse)
def list_storefront_product_qa(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
) -> StorefrontQaListResponse:
    """Public Q&A for a storefront product (frontstore PDP)."""
    _set_no_cache(response)
    service = StorefrontCatalogService(db)
    ec = service.get_ec_by_slug(slug)
    if not ec:
        raise HTTPException(status_code=404, detail="Product not found")
    qa = _load_public_qa(db, ec.catalog_product_id, limit=limit)
    return StorefrontQaListResponse(
        data=qa,
        meta=StorefrontQaListMeta(count=len(qa)),
    )


@router.post("/by-slug/{slug}/qa", response_model=StorefrontQaCreateResponse, status_code=201)
def create_storefront_product_qa(
    slug: str,
    payload: StorefrontQaCreate,
    db: Session = Depends(get_db),
    ctx: Optional[CustomerAuthContext] = Depends(get_optional_storefront_customer),
) -> StorefrontQaCreateResponse:
    """Shopper question → catalog_product_qa (pending until answered)."""
    _ec, product = _resolve_catalog_for_slug(db, slug)
    name = payload.customer_name.strip()
    if ctx and not name:
        name = ctx[2].name or "Customer"
    row = CatalogProductQa(
        id=str(uuid.uuid4()),
        question_number=_next_storefront_question_number(db),
        product_id=product.id,
        product_name=product.name,
        product_sku=product.sku or "",
        product_brand=product.brand,
        product_category=product.category,
        product_image_url=product.thumbnail,
        customer_name=name,
        question=payload.question.strip(),
        answer=None,
        status="pending",
        is_verified=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return StorefrontQaCreateResponse(data=_qa_to_read(row))


@router.get("/by-slug/{slug}", response_model=StorefrontProductDetailResponse)
def get_storefront_product_by_slug(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
    user: Optional[AuthUser] = Depends(get_optional_user),
) -> StorefrontProductDetailResponse:
    preview = _is_staff_preview(user)
    # A preview response is per-user, so it must never land in a shared cache.
    _set_cache(response, private=preview)
    service = StorefrontCatalogService(db, include_private=preview)
    view = service.get_by_slug(slug)
    if not view:
        raise HTTPException(status_code=404, detail="Product not found")
    ec = service.get_ec_by_slug(slug)
    if not ec:
        raise HTTPException(status_code=404, detail="Product not found")
    settings = db.get(WebsiteSettings, DEFAULT_WEBSITE_SETTINGS_ID)
    more_count = int(getattr(settings, "more_to_love_count", 6) or 6)
    return StorefrontProductDetailResponse(
        data=_detail_from_ec(view, ec, db),
        related=_attach_review_stats(db, service.more_to_love(slug, limit=more_count)),
        paired=_attach_review_stats(db, service.paired(slug)),
    )


@router.get("/{product_id}", response_model=StorefrontProductResponse)
def get_storefront_product_by_id(
    product_id: str,
    response: Response,
    db: Session = Depends(get_db),
) -> StorefrontProductResponse:
    _set_cache(response)
    service = StorefrontCatalogService(db)
    ec = (
        service._base_query()
        .filter(
            (EcommerceItem.catalog_product_id == product_id) | (EcommerceItem.item_id == product_id),
        )
        .first()
    )
    if not ec:
        raise HTTPException(status_code=404, detail="Product not found")
    view = service._items.resolve_storefront_from_ecommerce(ec)
    if not view:
        raise HTTPException(status_code=404, detail="Product not found")
    return StorefrontProductResponse(data=_attach_review_stats(db, [view])[0])
