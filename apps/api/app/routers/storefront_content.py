"""Public storefront content: CMS pages, settings, contact, blog, offers."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.blog_category import BlogCategory
from app.models.blog_comment import BlogComment
from app.models.blog_post import BlogPost
from app.models.blog_settings import DEFAULT_BLOG_SETTINGS_ID, BlogSettings
from app.models.marketing_coupon import MarketingCoupon
from app.models.newsletter_subscriber import NewsletterSubscriber
from app.models.website_contact_submission import WebsiteContactSubmission
from app.schemas.newsletter_subscriber import NewsletterSubscribeRequest, NewsletterSubscribeResponse
from app.models.website_page import WebsitePage, load_json
from app.models.website_settings import DEFAULT_WEBSITE_SETTINGS_ID, WebsiteSettings
from app.services.ecommerce.account_menu_settings import load_account_menu_settings
from app.services.ecommerce.builder_plugin_settings import load_builder_plugin_settings
from app.services.ecommerce.live_chat_settings import load_live_chat_enabled
from app.services.ecommerce.social_links_settings import load_social_links
from app.services.site_resolver import SITE_HOST_HEADER, resolve_site
from app.services.site_store_options import load_site_options
from app.services.ecommerce.checkout_tax_availability import (
    load_tax_settings,
    tax_is_included_in_price,
    tax_rate_percent,
)
from app.services.footer_links_sync import resolve_footer_links_for_site
from app.services.storefront_site_options import (
    build_catalog_options,
    build_commerce_options,
    build_storefront_options,
)
from app.services.ecommerce.storefront_catalog_service import StorefrontCatalogService
from app.services.ecommerce.storefront_feature_flags import resolve_storefront_feature_flags

router = APIRouter(tags=["storefront-content"])

STOREFRONT_CACHE = "public, max-age=60, s-maxage=120, stale-while-revalidate=300"
PRIVATE_CACHE = "private, no-store"


class StorefrontPageRead(BaseModel):
    id: str
    slug: str
    name: str
    title: str
    description: str = ""
    body_html: str = ""
    meta_title: str = ""
    meta_description: str = ""
    updated_at: Optional[str] = None


class StorefrontPageListItem(BaseModel):
    id: str
    slug: str
    name: str
    url: str
    page_type: str = "website"


class StorefrontPageListResponse(BaseModel):
    data: List[StorefrontPageListItem]
    meta: dict


class StorefrontPageResponse(BaseModel):
    data: StorefrontPageRead


class StorefrontSettingsRead(BaseModel):
    site_name: str
    tagline: str = ""
    logo_url: str = ""
    logo_mobile_url: str = ""
    favicon_url: str = ""
    address: str = ""
    contact_phone: str = ""
    contact_email: str = ""
    whatsapp_number: str = ""
    copyright_text: str = ""
    business_hours: str = ""
    primary_domain: str = ""
    storefront_url: str = ""
    currency: str = "BDT"
    timezone: str = "Asia/Dhaka"
    # Phase 4 — Center-synced storefront gates (storefront clients)
    client_slug: Optional[str] = None
    plan: Optional[str] = None
    entitlements_bound: bool = False
    feature_flags: dict = Field(
        default_factory=lambda: {
            "pc_builder": True,
            "wishlist": True,
            "emi": True,
            "china_import": True,
        }
    )
    enabled_modules: List[str] = Field(default_factory=list)
    # Which customer-panel menus the storefront should render.
    account_menu: dict = Field(default_factory=dict)
    # Which storefront builder tools (PC/CC Builder, calculators) are on —
    # from the Again Builder plugin in Settings → Plugins.
    builder_plugins: dict = Field(default_factory=dict)
    # Whether the Live Chat button/widget shows on the storefront at all.
    live_chat_enabled: bool = True
    # Public social profile URLs; empty means "no profile, hide the icon".
    social: dict = Field(default_factory=dict)
    # Per-site branding / chrome from workspace_sites.options_json.storefront.
    site_code: str = ""
    site_is_primary: bool = True
    storefront: dict = Field(default_factory=dict)
    # Listing display rules from the site's Option tab (items per page, stock
    # visibility, …).
    catalog: dict = Field(default_factory=dict)
    # Review / checkout / price gates from the same tab, plus the resolved tax
    # numbers the storefront needs to label prices.
    commerce: dict = Field(default_factory=dict)


class StorefrontSettingsResponse(BaseModel):
    data: StorefrontSettingsRead


class ContactCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=50)
    subject: str = Field(default="", max_length=255)
    message: str = Field(min_length=1, max_length=5000)


class ContactCreateResponse(BaseModel):
    data: dict


class BlogPostListItem(BaseModel):
    id: str
    slug: str
    title: str
    excerpt: Optional[str] = None
    cover_image_url: Optional[str] = None
    category_id: Optional[str] = None
    category_slug: Optional[str] = None
    category_name: Optional[str] = None
    author_name: Optional[str] = None
    published_at: Optional[datetime] = None


class BlogPostDetail(BlogPostListItem):
    content: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None


class BlogPostListResponse(BaseModel):
    data: List[BlogPostListItem]
    meta: dict


class BlogPostResponse(BaseModel):
    data: BlogPostDetail


class BlogCategoryRead(BaseModel):
    id: str
    slug: str
    name: str
    post_count: int = 0


class BlogCategoryListResponse(BaseModel):
    data: List[BlogCategoryRead]


class StorefrontBlogCommentCreate(BaseModel):
    author_name: str = Field(min_length=1, max_length=120)
    author_email: Optional[str] = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=5000)


class StorefrontBlogCommentRead(BaseModel):
    id: str
    author_name: str
    body: str
    created_at: datetime
    status: str


class StorefrontBlogCommentListResponse(BaseModel):
    data: List[StorefrontBlogCommentRead]
    meta: dict


class StorefrontBlogCommentResponse(BaseModel):
    data: StorefrontBlogCommentRead
    meta: dict = {}


class OfferCouponRead(BaseModel):
    code: str
    title: str
    description: str = ""
    discount_type: str
    discount_value: float
    status: str


class OffersResponse(BaseModel):
    data: dict


def _set_cache(response: Response, value: str = STOREFRONT_CACHE) -> None:
    response.headers["Cache-Control"] = value


def _page_title(page: WebsitePage) -> str:
    seo = load_json(page.seo_json, {})
    return str(seo.get("meta_title") or page.name or page.slug)


def _normalize_storefront_brand_text(value: str) -> str:
    if not value:
        return ""
    normalized = value.replace("TechPickly", "Excellent Technology BD")
    normalized = normalized.replace("Againcart", "Excellent Technology BD")
    return normalized


def _is_storefront_content_page(page: WebsitePage) -> bool:
    flags = load_json(page.flags_json, {})
    if flags.get("is_home") or flags.get("is_system"):
        return False
    if page.page_type in ("website", "custom", "landing", "blog"):
        return True
    return False


PAGE_SLUG_ALIASES: dict[str, list[str]] = {
    "about-us": ["about"],
    "about": ["about-us"],
    "terms-and-conditions": ["terms"],
    "terms": ["terms-and-conditions"],
    "refund-and-return": ["refund-return"],
    "refund-and-return-policy": ["refund-return", "refund-and-return"],
    "refund-return": ["refund-and-return-policy", "refund-and-return"],
    "return-policy": ["refund-return", "refund-and-return"],
    "delivery-policy": ["online-delivery", "shipping-charge", "delivery"],
    "shipping-charge": ["online-delivery", "delivery-policy", "delivery"],
    "online-delivery": ["shipping-charge", "delivery-policy", "delivery"],
    "delivery": ["online-delivery", "shipping-charge"],
    "payment-terms": ["payment", "payments"],
    "warranty-policy": ["warranty"],
    "privacy-policy": ["privacy"],
    "privacy": ["privacy-policy"],
    "contact-us": ["contact"],
    "contact": ["contact-us"],
}


def page_slug_candidates(slug: str) -> list[str]:
    clean = (slug or "").strip().lower().lstrip("/")
    candidates = [clean, *PAGE_SLUG_ALIASES.get(clean, [])]
    seen: set[str] = set()
    ordered: list[str] = []
    for item in candidates:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def find_published_website_page(db: Session, slug: str) -> Optional[WebsitePage]:
    ordered = page_slug_candidates(slug)
    if not ordered:
        return None
    page = (
        db.query(WebsitePage)
        .filter(WebsitePage.slug.in_(ordered))
        .filter(WebsitePage.status == "published")
        .filter(WebsitePage.visibility == "public")
        .first()
    )
    if page is None or not _is_storefront_content_page(page):
        return None
    return page


@router.get("/pages", response_model=StorefrontPageListResponse)
def list_storefront_pages(
    response: Response,
    db: Session = Depends(get_db),
) -> StorefrontPageListResponse:
    """Published public CMS pages for footer / information links (live-edit)."""
    _set_cache(response)
    rows = (
        db.query(WebsitePage)
        .filter(WebsitePage.status == "published")
        .filter(WebsitePage.visibility == "public")
        .order_by(WebsitePage.name.asc())
        .all()
    )
    data: List[StorefrontPageListItem] = []
    for page in rows:
        if not _is_storefront_content_page(page):
            continue
        slug = (page.slug or "").strip()
        if not slug:
            continue
        url = (page.url or "").strip() or f"/{slug.lstrip('/')}"
        if not url.startswith("/"):
            url = f"/{url}"
        data.append(
            StorefrontPageListItem(
                id=page.id,
                slug=slug,
                name=page.name,
                url=url,
                page_type=page.page_type or "website",
            )
        )
    return StorefrontPageListResponse(data=data, meta={"count": len(data)})


@router.get("/pages/{slug}", response_model=StorefrontPageResponse)
def get_storefront_page(slug: str, response: Response, db: Session = Depends(get_db)) -> StorefrontPageResponse:
    _set_cache(response)
    page = find_published_website_page(db, slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    seo = load_json(page.seo_json, {})
    title = _normalize_storefront_brand_text(_page_title(page))
    description = _normalize_storefront_brand_text(page.description or "")
    body_html = _normalize_storefront_brand_text(page.body_html or "")
    meta_title = _normalize_storefront_brand_text(str(seo.get("meta_title") or page.name))
    meta_description = _normalize_storefront_brand_text(
        str(seo.get("meta_description") or page.description or "")
    )
    return StorefrontPageResponse(
        data=StorefrontPageRead(
            id=page.id,
            slug=page.slug,
            name=_normalize_storefront_brand_text(page.name),
            title=title,
            description=description,
            body_html=body_html,
            meta_title=meta_title,
            meta_description=meta_description,
            updated_at=page.updated_at.isoformat() if page.updated_at else None,
        )
    )


@router.get("/settings", response_model=StorefrontSettingsResponse)
def get_storefront_settings(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> StorefrontSettingsResponse:
    # Brand logos change often from Sites / live-edit — avoid stale header logo.
    # Vary on the host header so two storefronts never share a cached response.
    _set_cache(response, "public, max-age=5, s-maxage=15, stale-while-revalidate=30")
    response.headers["Vary"] = SITE_HOST_HEADER

    site = resolve_site(db, request)
    row = db.get(WebsiteSettings, DEFAULT_WEBSITE_SETTINGS_ID)
    if not row:
        row = WebsiteSettings(id=DEFAULT_WEBSITE_SETTINGS_ID)

    site_name = (site.name if site and site.name else None) or row.site_name or "Store"
    tagline = (site.tagline if site else None) or row.tagline or ""
    logo_url = (site.logo_url if site else None) or row.logo_url or ""
    logo_mobile_url = (site.logo_mobile_url if site else None) or row.logo_mobile_url or ""
    favicon_url = (site.favicon_url if site else None) or row.favicon_url or ""

    def _norm(u: str) -> str:
        v = (u or "").strip()
        if not v:
            return ""
        if v.startswith("/uploads/"):
            return v
        idx = v.find("/uploads/")
        return v[idx:] if idx >= 0 else v

    logo_url = _norm(logo_url)
    logo_mobile_url = _norm(logo_mobile_url) or logo_url
    favicon_url = _norm(favicon_url)
    address = (site.address if site else None) or row.address or ""
    contact_phone = (site.contact_phone if site else None) or row.contact_phone or ""
    contact_email = (site.contact_email if site else None) or row.contact_email or ""
    whatsapp_number = (site.whatsapp_number if site else None) or row.whatsapp_number or ""
    copyright_text = (site.copyright_text if site else None) or row.copyright_text or ""
    business_hours = (site.business_hours if site else "") or ""
    primary_domain = (site.primary_domain if site else "") or ""
    storefront_url = ""
    currency = "BDT"
    timezone = "Asia/Dhaka"
    if site:
        storefront_url = (
            site.storefront_url_production
            or site.storefront_url_preview
            or site.storefront_url_local
            or ""
        )
        currency = site.currency or currency
        timezone = site.timezone or timezone

    site_options = load_site_options(site.options_json if site else None)
    storefront_options = build_storefront_options(site_options)
    if site and not storefront_options.get("footer", {}).get("links"):
        resolved_links = resolve_footer_links_for_site(site, db)
        if resolved_links:
            storefront_options = {
                **storefront_options,
                "footer": {
                    **storefront_options.get("footer", {}),
                    "links": resolved_links,
                },
            }
    catalog_options = build_catalog_options(site_options)
    commerce_options = {
        **build_commerce_options(site_options),
        "tax_label": load_tax_settings(db).get("tax.label") or "VAT",
        "tax_rate_percent": float(tax_rate_percent(db)),
        "tax_included_in_price": tax_is_included_in_price(db),
    }
    # Site-level links win; the global platform_settings values remain as a
    # fallback so links configured before the move keep working.
    platform_social = load_social_links(db)
    social = {
        name: (storefront_options["social"].get(name) or platform_social.get(name) or "")
        for name in {*storefront_options["social"], *platform_social}
    }

    entitlements = resolve_storefront_feature_flags()
    return StorefrontSettingsResponse(
        data=StorefrontSettingsRead(
            site_name=site_name,
            tagline=tagline,
            logo_url=logo_url,
            logo_mobile_url=logo_mobile_url,
            favicon_url=favicon_url,
            address=address,
            contact_phone=contact_phone,
            contact_email=contact_email,
            whatsapp_number=whatsapp_number,
            copyright_text=copyright_text,
            business_hours=business_hours,
            primary_domain=primary_domain,
            storefront_url=storefront_url,
            currency=currency,
            timezone=timezone,
            client_slug=entitlements.get("client_slug"),
            plan=entitlements.get("plan") or (site.plan if site else None),
            entitlements_bound=bool(entitlements.get("bound")),
            feature_flags=entitlements.get("feature_flags") or {},
            enabled_modules=list(entitlements.get("enabled_modules") or []),
            account_menu=load_account_menu_settings(db),
            builder_plugins=load_builder_plugin_settings(db),
            live_chat_enabled=load_live_chat_enabled(db),
            social=social,
            site_code=(site.code if site and site.code else ""),
            site_is_primary=bool(site.is_primary) if site else True,
            storefront=storefront_options,
            catalog=catalog_options,
            commerce=commerce_options,
        )
    )


@router.get("/builder-tools/{tool_slug}")
def get_builder_tool_config_public(tool_slug: str, db: Session = Depends(get_db)) -> dict:
    """A builder tool's effective slot/label/category config — an admin's
    saved override if there is one, otherwise the tool's built-in default.
    Public: the storefront's PC/CC Builder pages read this with no login."""
    from app.services.ecommerce.builder_tool_config import DEFAULTS_BY_TOOL, load_tool_config

    if tool_slug not in DEFAULTS_BY_TOOL:
        raise HTTPException(status_code=404, detail="Unknown builder tool")
    return {"data": load_tool_config(db, tool_slug)}


@router.post("/contact", response_model=ContactCreateResponse)
def submit_contact(
    payload: ContactCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> ContactCreateResponse:
    _set_cache(response, PRIVATE_CACHE)
    if not payload.email.strip() and not payload.phone.strip():
        raise HTTPException(status_code=400, detail="Email or phone is required")
    row = WebsiteContactSubmission(
        name=payload.name.strip(),
        email=payload.email.strip(),
        phone=payload.phone.strip(),
        subject=payload.subject.strip() or "Website inquiry",
        message=payload.message.strip(),
        status="new",
    )
    db.add(row)
    db.commit()
    return ContactCreateResponse(data={"id": row.id, "status": "received"})


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
_BD_PHONE_RE = re.compile(r"^(?:\+?880|0)1[3-9]\d{8}$")


@router.post("/newsletter/subscribe", response_model=NewsletterSubscribeResponse)
def subscribe_newsletter(
    payload: NewsletterSubscribeRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> NewsletterSubscribeResponse:
    """Footer "Subscribe" opt-in — the visitor gives an email or a BD mobile
    number, whichever they have to hand. Re-submitting the same contact just
    re-activates it rather than creating a duplicate row."""
    _set_cache(response, PRIVATE_CACHE)
    contact = payload.contact.strip()
    digits = contact.replace(" ", "").replace("-", "")
    is_email = bool(_EMAIL_RE.match(contact))
    is_phone = bool(_BD_PHONE_RE.match(digits))
    if not is_email and not is_phone:
        raise HTTPException(status_code=400, detail="Enter a valid email or mobile number")

    email = contact if is_email else ""
    phone = digits if is_phone else ""
    existing = (
        db.query(NewsletterSubscriber)
        .filter(NewsletterSubscriber.email == email if is_email else NewsletterSubscriber.phone == phone)
        .first()
    )
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.commit()
        return NewsletterSubscribeResponse(data={"status": "subscribed"})

    row = NewsletterSubscriber(email=email, phone=phone, source="footer")
    db.add(row)
    db.commit()
    return NewsletterSubscribeResponse(data={"status": "subscribed"})


@router.get("/blog/posts", response_model=BlogPostListResponse)
def list_blog_posts(
    response: Response,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    category: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
) -> BlogPostListResponse:
    _set_cache(response)
    query = db.query(BlogPost).filter(BlogPost.status == "published")
    if category:
        cat = db.query(BlogCategory).filter(BlogCategory.slug == category).first()
        if cat:
            query = query.filter(BlogPost.category_id == cat.id)
        else:
            query = query.filter(BlogPost.category_name.ilike(category))
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        query = query.filter(
            (BlogPost.title.ilike(like))
            | (BlogPost.excerpt.ilike(like))
            | (BlogPost.content.ilike(like))
        )
    total = query.count()
    rows = (
        query.order_by(BlogPost.published_at.desc().nullslast(), BlogPost.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    cat_ids = {r.category_id for r in rows if r.category_id}
    cat_by_id = {}
    if cat_ids:
        cat_by_id = {
            c.id: c
            for c in db.query(BlogCategory).filter(BlogCategory.id.in_(cat_ids)).all()
        }
    return BlogPostListResponse(
        data=[
            BlogPostListItem(
                id=r.id,
                slug=r.slug,
                title=r.title,
                excerpt=r.excerpt,
                cover_image_url=r.cover_image_url,
                category_id=r.category_id,
                category_slug=(cat_by_id[r.category_id].slug if r.category_id in cat_by_id else None),
                category_name=r.category_name,
                author_name=r.author_name,
                published_at=r.published_at,
            )
            for r in rows
        ],
        meta={"count": total, "page": page, "per_page": per_page},
    )


@router.get("/blog/posts/{slug}", response_model=BlogPostResponse)
def get_blog_post(slug: str, response: Response, db: Session = Depends(get_db)) -> BlogPostResponse:
    _set_cache(response)
    row = (
        db.query(BlogPost)
        .filter(BlogPost.slug == slug, BlogPost.status == "published")
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    cat_slug = None
    if row.category_id:
        cat = db.get(BlogCategory, row.category_id)
        if cat:
            cat_slug = cat.slug
    return BlogPostResponse(
        data=BlogPostDetail(
            id=row.id,
            slug=row.slug,
            title=row.title,
            excerpt=row.excerpt,
            cover_image_url=row.cover_image_url,
            category_id=row.category_id,
            category_slug=cat_slug,
            category_name=row.category_name,
            author_name=row.author_name,
            published_at=row.published_at,
            content=row.content,
            seo_title=row.seo_title,
            seo_description=row.seo_description,
        )
    )


@router.get("/blog/categories", response_model=BlogCategoryListResponse)
def list_blog_categories(response: Response, db: Session = Depends(get_db)) -> BlogCategoryListResponse:
    """Active blog categories from admin (Blog → Categories), with published post counts."""
    _set_cache(response)
    rows = (
        db.query(BlogCategory, func.count(BlogPost.id).label("post_count"))
        .outerjoin(
            BlogPost,
            (BlogPost.category_id == BlogCategory.id) & (BlogPost.status == "published"),
        )
        .filter(BlogCategory.status == "active")
        .group_by(BlogCategory.id)
        .order_by(BlogCategory.sort_order.asc(), BlogCategory.name.asc())
        .all()
    )
    return BlogCategoryListResponse(
        data=[
            BlogCategoryRead(id=cat.id, slug=cat.slug, name=cat.name, post_count=int(count or 0))
            for cat, count in rows
        ]
    )


def _blog_settings(db: Session) -> BlogSettings:
    row = db.get(BlogSettings, DEFAULT_BLOG_SETTINGS_ID)
    if row:
        return row
    row = BlogSettings(id=DEFAULT_BLOG_SETTINGS_ID)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _published_post_by_slug(db: Session, slug: str) -> BlogPost:
    row = (
        db.query(BlogPost)
        .filter(BlogPost.slug == slug, BlogPost.status == "published")
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    return row


@router.get("/blog/posts/{slug}/comments", response_model=StorefrontBlogCommentListResponse)
def list_blog_post_comments(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
) -> StorefrontBlogCommentListResponse:
    _set_cache(response, PRIVATE_CACHE)
    post = _published_post_by_slug(db, slug)
    settings = _blog_settings(db)
    rows = (
        db.query(BlogComment)
        .filter(BlogComment.post_id == post.id, BlogComment.status == "approved")
        .order_by(BlogComment.created_at.asc())
        .all()
    )
    return StorefrontBlogCommentListResponse(
        data=[
            StorefrontBlogCommentRead(
                id=r.id,
                author_name=r.author_name,
                body=r.body,
                created_at=r.created_at,
                status=r.status,
            )
            for r in rows
        ],
        meta={
            "count": len(rows),
            "comments_enabled": bool(settings.comments_enabled),
            "moderate_comments": bool(settings.moderate_comments),
        },
    )


@router.post("/blog/posts/{slug}/comments", response_model=StorefrontBlogCommentResponse)
def create_blog_post_comment(
    slug: str,
    payload: StorefrontBlogCommentCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> StorefrontBlogCommentResponse:
    _set_cache(response, PRIVATE_CACHE)
    post = _published_post_by_slug(db, slug)
    settings = _blog_settings(db)
    if not settings.comments_enabled:
        raise HTTPException(status_code=400, detail="Comments are disabled")

    name = payload.author_name.strip()
    body = payload.body.strip()
    email = (payload.author_email or "").strip() or None
    if not name or not body:
        raise HTTPException(status_code=400, detail="Name and comment are required")

    status = "pending" if settings.moderate_comments else "approved"
    row = BlogComment(
        post_id=post.id,
        article_title=post.title,
        author_name=name,
        author_email=email,
        body=body,
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return StorefrontBlogCommentResponse(
        data=StorefrontBlogCommentRead(
            id=row.id,
            author_name=row.author_name,
            body=row.body,
            created_at=row.created_at,
            status=row.status,
        ),
        meta={
            "comments_enabled": True,
            "moderate_comments": bool(settings.moderate_comments),
            "awaiting_moderation": status == "pending",
        },
    )


@router.get("/offers", response_model=OffersResponse)
def get_offers(
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(24, ge=1, le=48),
) -> OffersResponse:
    _set_cache(response)
    today = date.today()
    coupons = (
        db.query(MarketingCoupon)
        .filter(MarketingCoupon.status == "active")
        .filter(MarketingCoupon.starts_at <= today)
        .filter(MarketingCoupon.ends_at >= today)
        .order_by(MarketingCoupon.updated_at.desc())
        .limit(20)
        .all()
    )
    coupon_reads = [
        OfferCouponRead(
            code=c.code,
            title=c.name or c.code,
            description=c.discount_label or "",
            discount_type=c.discount_type,
            discount_value=float(c.discount_value or 0),
            status=c.status,
        )
        for c in coupons
    ]

    catalog = StorefrontCatalogService(db)
    sale = catalog.list_products(on_sale=True, per_page=limit, page=1)
    products = sale.items
    if not products:
        products = catalog.featured(limit=limit)

    return OffersResponse(
        data={
            "coupons": [c.model_dump() for c in coupon_reads],
            "products": [
                {
                    "id": view.id,
                    "item_id": view.item_id,
                    "slug": view.slug,
                    "name": view.name,
                    "price": float(view.price),
                    "compare_at_price": float(view.compare_at_price)
                    if view.compare_at_price is not None
                    else None,
                    "thumbnail": view.thumbnail,
                    "brand": view.brand,
                    "in_stock": view.in_stock,
                }
                for view in products
            ],
        }
    )
