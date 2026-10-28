from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class HeroSlide(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    image_url: str = Field(max_length=500)
    href: str = Field(default="/", max_length=500)
    alt: str = Field(default="", max_length=255)
    object_fit: Literal["fill", "fit"] = "fill"
    image_width: Optional[int] = Field(default=None, ge=1)
    image_height: Optional[int] = Field(default=None, ge=1)
    hidden: bool = False


class HeroSection(BaseModel):
    autoplay_ms: int = Field(default=3000, ge=0, le=60_000)
    slides: List[HeroSlide] = Field(default_factory=list)


class CategoryCarouselItem(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    category_id: str = Field(min_length=1, max_length=64)
    # Optional display-name override — empty uses the category's own name.
    label: str = Field(default="", max_length=120)
    # Optional homepage override — empty uses catalog banner/icon.
    image_url: str = Field(default="", max_length=500)
    # Optional custom link — empty uses /{category.slug}.
    href: str = Field(default="", max_length=500)
    hidden: bool = False


class CategoriesSection(BaseModel):
    """Homepage category carousel. Empty items = automatic featured categories."""

    title: str = Field(default="Shop by Category", max_length=200)
    subtitle: str = Field(default="Jump straight to the department you're after.", max_length=300)
    hidden: bool = False
    items: List[CategoryCarouselItem] = Field(default_factory=list)


class NoticeSection(BaseModel):
    """Homepage notice / announcement bar (scrolling marquee)."""

    hidden: bool = False
    text: str = Field(
        default=(
            "Tuesday, 21 July, All our branches are open including Elephant Road branch. "
            "Additionally, our online activities are open and operational. Please check our "
            "contact page for the schedule."
        ),
        max_length=500,
    )


class SeoBlock(BaseModel):
    """One card in the homepage SEO content grid."""

    id: str = Field(min_length=1, max_length=64)
    icon: str = Field(default="", max_length=120)
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=3000)
    hidden: bool = False


def default_seo_blocks() -> List["SeoBlock"]:
    return [
        SeoBlock(
            id="laptop",
            icon="laptop_mac",
            title="Laptop Shop in Dhaka",
            body=(
                "Excellent Technology BD carries the latest laptops from ASUS, Lenovo, HP, Dell, MSI, Acer and Apple — "
                "for students, office work, freelancing and gaming. Every laptop comes with official "
                "warranty, and our team helps you pick the right model for your budget."
            ),
        ),
        SeoBlock(
            id="desktop",
            icon="desktop_windows",
            title="Desktop PC & PC Builder",
            body=(
                "Buy a ready desktop PC or build your own with our PC Builder. Pick compatible parts, "
                "compare prices and get your PC assembled and tested by our technicians."
            ),
        ),
        SeoBlock(
            id="gaming",
            icon="sports_esports",
            title="Gaming PC, Monitors & Accessories",
            body=(
                "High-refresh gaming monitors, graphics cards, consoles, gaming chairs and accessories "
                "from leading brands — everything for your battlestation in one place."
            ),
        ),
        SeoBlock(
            id="branches",
            icon="storefront",
            title="Three Branches in Dhaka",
            body=(
                "Visit us at BCS Computer City (IDB Bhaban, Agargaon), Multiplan Center (New Elephant "
                "Road) or Shah Ali Plaza (Mirpur 10) to see products in person, or order online with "
                "home delivery."
            ),
        ),
        SeoBlock(
            id="service",
            icon="local_shipping",
            title="Fast Delivery & After-sales Support",
            body=(
                "Same-day delivery inside Dhaka and courier delivery across Bangladesh, with EMI, "
                "bKash, Nagad, card and cash on delivery payments and reliable warranty support."
            ),
        ),
    ]


class SeoSection(BaseModel):
    """Homepage SEO content block (bottom of the home page)."""

    hidden: bool = False
    badge_text: str = Field(default="About Excellent Technology BD", max_length=120)
    heading: str = Field(
        default="Leading Computer, Laptop & Gaming PC Retail & Online Shop in Bangladesh",
        max_length=300,
    )
    intro_text: str = Field(
        default=(
            "Excellent Technology BD is a Dhaka-based computer and IT retailer with three branches — IDB Bhaban, "
            "Multiplan and Mirpur 10. We sell genuine laptops, desktops, monitors, components and "
            "accessories with official warranty, and deliver across Bangladesh."
        ),
        max_length=2000,
    )
    blocks: List[SeoBlock] = Field(default_factory=default_seo_blocks)


class CategoryContentBlock(BaseModel):
    """One heading+paragraph block in the category-page info panel."""

    id: str = Field(min_length=1, max_length=64)
    heading: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=3000)
    hidden: bool = False


def default_category_content_blocks() -> List["CategoryContentBlock"]:
    return [
        CategoryContentBlock(
            id="guide",
            heading="Your Complete Guide to Every Category, Brand, and Budget",
            body=(
                "Whether you're building a home office, upgrading your gaming setup, or just fixing up "
                "the house, finding the right tech at the right price matters. From personal AI "
                "supercomputers to power stations, monitors, laptops, and even appliances, we bring "
                "brings together every category you need in one place. Prices for the same class of "
                "product can vary wildly between brands and retailers, which is why we keep this listing "
                "fresh with real stock and real prices.\n\n"
                "This page brings together our most popular picks across every department so you can "
                "compare specs, prices, and discounts in one scroll. Filter by price range or "
                "availability on the left, sort by price or name at the top, and browse with confidence "
                "knowing every listing here is currently in stock."
            ),
        ),
        CategoryContentBlock(
            id="pricing",
            heading="What Should You Expect to Pay in Bangladesh Right Now?",
            body=(
                "Pricing depends heavily on the category. Entry-level accessories like earbuds start "
                "under BDT 1,000, while flagship gaming laptops and AI workstations can run past BDT 6 "
                "lakh. Mid-range categories such as monitors, desktops, and power stations typically fall "
                "between BDT 15,000 and BDT 1,20,000, making them the sweet spot for most home and office "
                "buyers.\n\n"
                "Whatever your budget, using the price filter on this page is the fastest way to narrow "
                "down your options without losing time comparing tabs across different sites."
            ),
        ),
    ]


class CategoryPriceRow(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    category: str = Field(default="", max_length=120)
    price_from: str = Field(default="", max_length=40)
    price_to: str = Field(default="", max_length=40)
    known_for: str = Field(default="", max_length=200)


def default_category_price_rows() -> List["CategoryPriceRow"]:
    return [
        CategoryPriceRow(id="desktop", category="Desktop PC", price_from="37,200", price_to="699,999", known_for="Brand PC, AI workstation, custom builds"),
        CategoryPriceRow(id="laptop", category="Laptop", price_from="27,500", price_to="630,000", known_for="Ultrabook, gaming laptop, 2-in-1 convertible"),
        CategoryPriceRow(id="monitor", category="Monitor", price_from="4,800", price_to="10,950", known_for="IPS panel, gaming, high refresh rate"),
        CategoryPriceRow(id="power", category="Power Backup", price_from="24,590", price_to="40,000", known_for="Portable power station, solar-ready UPS"),
        CategoryPriceRow(id="gadget", category="Gadget & Accessories", price_from="799", price_to="117,000", known_for="Earbuds, drones, gaming consoles"),
        CategoryPriceRow(id="appliance", category="Home Appliance", price_from="15,916", price_to="73,000", known_for="AC, washing machine, sewing machine"),
    ]


class CategoryContentSection(BaseModel):
    """Generic informational block + price-comparison table shown at the
    bottom of every category listing page (same content site-wide, not
    per-category)."""

    hidden: bool = False
    blocks: List[CategoryContentBlock] = Field(default_factory=default_category_content_blocks)
    price_table_title: str = Field(
        default="Category-Wise Price Comparison – Bangladesh",
        max_length=200,
    )
    price_table: List[CategoryPriceRow] = Field(default_factory=default_category_price_rows)


class BannerSlide(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    image_url: str = Field(default="", max_length=500)
    href: str = Field(default="/", max_length=500)
    alt: str = Field(default="", max_length=255)
    object_fit: Literal["fill", "fit"] = "fill"
    image_width: Optional[int] = Field(default=None, ge=1)
    image_height: Optional[int] = Field(default=None, ge=1)
    hidden: bool = False


class BannersSection(BaseModel):
    """Homepage dual banner strip."""

    slides: List[BannerSlide] = Field(default_factory=list)


class FeaturedTab(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="Featured", max_length=120)
    # default = auto feed from storefront; custom = product_ids list
    mode: Literal["default", "custom"] = "default"
    default_source: Literal["featured", "newest", "bestsellers"] = "featured"
    product_ids: List[str] = Field(default_factory=list)
    hidden: bool = False


class FeaturedProductsSection(BaseModel):
    """Homepage Most Wanted / featured product tabs."""

    title: str = Field(default="Most Wanted", max_length=200)
    subtitle: str = Field(default="Explore Our Best-Selling Deal", max_length=300)
    autoplay_ms: int = Field(default=0, ge=0, le=60_000)
    tabs: List[FeaturedTab] = Field(default_factory=list)


class BrandCarouselItem(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    brand_id: str = Field(min_length=1, max_length=64)
    # Optional homepage override — empty uses catalog logo.
    image_url: str = Field(default="", max_length=500)
    # Optional custom link — empty uses /{brand.slug}.
    href: str = Field(default="", max_length=500)
    hidden: bool = False


class BrandsSection(BaseModel):
    """Homepage brand strip. Empty items = all active catalog brands."""

    title: str = Field(default="Brands We Distribute", max_length=200)
    subtitle: str = Field(default="Official distributor of trusted brands.", max_length=300)
    autoplay_ms: int = Field(default=0, ge=0, le=60_000)
    items: List[BrandCarouselItem] = Field(default_factory=list)


class AboutSection(BaseModel):
    """Homepage about / company story box."""

    title: str = Field(default="Excellent Technology BD", max_length=200)
    subtitle: str = Field(
        default="A Trusted Computer Distributor & Retailer in Bangladesh",
        max_length=300,
    )
    collapse_enabled: bool = True
    body_html: str = Field(default="")


class SupportSection(BaseModel):
    """Homepage support / contact strip."""

    title: str = Field(default="Support", max_length=200)
    subtitle: str = Field(default="Official distributor of trusted brands.", max_length=300)
    phone: str = Field(default="01913-004278", max_length=64)
    phone_href: str = Field(default="tel:+8801913004278", max_length=120)
    whatsapp: str = Field(default="01913-004278", max_length=64)
    whatsapp_href: str = Field(default="https://wa.me/8801913004278", max_length=300)
    hours: str = Field(default="10:00 AM - 08:00 PM", max_length=120)
    phone_icon_url: str = Field(default="", max_length=500)
    agent_image_url: str = Field(default="", max_length=500)
    store_label: str = Field(default="Store Locator", max_length=120)
    store_title: str = Field(default="Find our Stores", max_length=200)
    store_href: str = Field(default="/outlets", max_length=500)
    store_icon_url: str = Field(default="", max_length=500)


class SideMenuItem(BaseModel):
    """Floating left rail icon button."""

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=120)
    href: str = Field(default="#", max_length=500)
    # Optional Font Awesome class — when set, overrides icon_url
    icon: str = Field(default="", max_length=120)
    # Default image icon (original SVG / media)
    icon_url: str = Field(default="", max_length=500)
    active: bool = False
    hidden: bool = False


class SideMenuSection(BaseModel):
    """Storefront floating toolbar (left rail)."""

    enabled: bool = True
    logo_url: str = Field(default="", max_length=500)
    logo_href: str = Field(default="/", max_length=500)
    items: List[SideMenuItem] = Field(default_factory=list)


class HeaderLinkItem(BaseModel):
    """Header action link (Order Track / PC Builder)."""

    label: str = Field(default="", max_length=120)
    href: str = Field(default="/", max_length=500)
    icon: str = Field(default="", max_length=120)
    icon_url: str = Field(default="", max_length=500)
    hidden: bool = False


class HeaderMobileSection(BaseModel):
    """Storefront mobile header chrome (logo + search)."""

    enabled: bool = True
    logo_url: str = Field(default="", max_length=500)
    logo_href: str = Field(default="/", max_length=500)
    search_placeholder: str = Field(default="Search Products", max_length=120)


class HeaderMenuItem(BaseModel):
    """One row of the header's "Builder" dropdown (desktop only)."""

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=120)
    href: str = Field(default="/", max_length=500)
    icon: str = Field(default="", max_length=120)
    hidden: bool = False


def default_builder_menu_items() -> List["HeaderMenuItem"]:
    return [
        HeaderMenuItem(id="pc-builder", label="PC Builder", href="/pc-builder", icon="memory"),
        HeaderMenuItem(id="cc-builder", label="CC Builder", href="/cc-builder", icon="videocam"),
        HeaderMenuItem(id="storage-calculator", label="Storage Calculator", href="/storage-calculator", icon="storage"),
        HeaderMenuItem(id="power-calculator", label="Power Calculator", href="/power-calculator", icon="bolt"),
    ]


class HeaderMenuSection(BaseModel):
    """The header's "Builder" dropdown trigger + its items (desktop only)."""

    label: str = Field(default="Builder", max_length=120)
    hidden: bool = False
    items: List[HeaderMenuItem] = Field(default_factory=default_builder_menu_items)


class HeaderSection(BaseModel):
    """Storefront header chrome — desktop fields + nested mobile."""

    enabled: bool = True
    logo_url: str = Field(default="", max_length=500)
    logo_href: str = Field(default="/", max_length=500)
    search_placeholder: str = Field(default="Search Products", max_length=120)
    order_track: HeaderLinkItem = Field(
        default_factory=lambda: HeaderLinkItem(label="Order Track", href="/order-track")
    )
    pc_builder: HeaderLinkItem = Field(
        default_factory=lambda: HeaderLinkItem(label="PC Builder", href="/pc-builder")
    )
    happy_hour: HeaderLinkItem = Field(
        default_factory=lambda: HeaderLinkItem(label="Happy Hour", href="/happy-hour")
    )
    builder_menu: HeaderMenuSection = Field(default_factory=HeaderMenuSection)
    mobile: HeaderMobileSection = Field(default_factory=HeaderMobileSection)


class FooterSocialItem(BaseModel):
    """Footer social icon link. `icon` is a legacy built-in key (whatsapp /
    facebook / instagram / youtube / tiktok) the storefront still draws a
    vector glyph for; `icon_url` is an admin-uploaded image, letting the
    admin add any platform without a code change. An empty `href` falls
    back to the matching field in Site Settings."""

    id: str = Field(..., max_length=40)
    icon: str = Field(default="", max_length=40)
    icon_url: str = Field(default="", max_length=500)
    label: str = Field(default="", max_length=60)
    href: str = Field(default="", max_length=500)
    hidden: bool = False


def default_footer_socials() -> List["FooterSocialItem"]:
    return [
        FooterSocialItem(id="whatsapp", icon="whatsapp", label="WhatsApp"),
        FooterSocialItem(id="facebook", icon="facebook", label="Facebook"),
        FooterSocialItem(id="youtube", icon="youtube", label="YouTube"),
        FooterSocialItem(id="instagram", icon="instagram", label="Instagram"),
    ]


class FooterMembershipItem(BaseModel):
    """Footer membership/association logo (BCS, e-CAB, ...)."""

    id: str = Field(..., max_length=40)
    name: str = Field(default="", max_length=200)
    image_url: str = Field(default="", max_length=500)
    hidden: bool = False


def default_footer_memberships() -> List["FooterMembershipItem"]:
    return [
        FooterMembershipItem(
            id="bcs",
            name="Bangladesh Computer Samity (BCS)",
            image_url="/images/membership/bcs-logo.png",
        ),
        FooterMembershipItem(
            id="ecs",
            name="E-Commerce Society (ECS)",
            image_url="/images/membership/ecs-logo.png",
        ),
        FooterMembershipItem(id="ecab", name="e-CAB", image_url="/images/membership/ecab.png"),
    ]


class FooterMobileSection(BaseModel):
    """Storefront mobile footer overrides."""

    enabled: bool = True
    logo_url: str = Field(default="", max_length=500)
    about_text: str = Field(default="", max_length=2000)
    hide_socials: bool = False
    hide_membership: bool = False
    hide_payment: bool = False


class FooterSection(BaseModel):
    """Storefront footer chrome — desktop fields + nested mobile; links via footer.links slot."""

    enabled: bool = True
    logo_url: str = Field(default="", max_length=500)
    logo_alt: str = Field(default="Excellent Technology BD", max_length=200)
    about_text: str = Field(default="", max_length=2000)
    socials: List[FooterSocialItem] = Field(default_factory=default_footer_socials)
    memberships: List[FooterMembershipItem] = Field(default_factory=default_footer_memberships)
    links_title: str = Field(default="Information", max_length=120)
    membership_title: str = Field(default="Membership", max_length=120)
    membership_logo_url: str = Field(default="", max_length=500)
    head_office_text: str = Field(default="", max_length=1000)
    copyright_text: str = Field(default="", max_length=500)
    payment_image_url: str = Field(default="/images/sslcommerz.png", max_length=500)
    # Contact/support block — previously always read from Site Settings; kept
    # editable here too so Live Edit can fully override it per-storefront.
    site_name: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=50)
    phone_hours_label: str = Field(default="9 AM - 8 PM", max_length=100)
    whatsapp_number: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=255)
    mobile: FooterMobileSection = Field(default_factory=FooterMobileSection)


HomepageBodySectionType = Literal[
    "hero",
    "categories",
    "banners",
    "featured",
    "brands",
    "about",
    "support",
    # Legacy / extended homepage sections (stored in DB layout)
    "category_promo",
    "video_gallery",
    "gallery_carousel",
    "category_rails",
    "you_may_love",
]


class LayoutBlock(BaseModel):
    """Ordered homepage body section instance."""

    id: str = Field(..., min_length=1, max_length=64)
    # Accept known + future section keys so GET /homepage never 500s on older JSON.
    type: str = Field(..., min_length=1, max_length=64)
    hidden: bool = False


def default_homepage_layout() -> List[LayoutBlock]:
    return [
        LayoutBlock(id="hero", type="hero"),
        LayoutBlock(id="categories", type="categories"),
        LayoutBlock(id="banners", type="banners"),
        LayoutBlock(id="featured", type="featured"),
        LayoutBlock(id="brands", type="brands"),
        LayoutBlock(id="about", type="about"),
        LayoutBlock(id="support", type="support"),
    ]


class HomepageContent(BaseModel):
    model_config = {"extra": "ignore"}

    hero: HeroSection = Field(default_factory=HeroSection)
    notice: NoticeSection = Field(default_factory=NoticeSection)
    categories: CategoriesSection = Field(default_factory=CategoriesSection)
    banners: BannersSection = Field(default_factory=BannersSection)
    happy_hour_promo: BannerSlide = Field(
        default_factory=lambda: BannerSlide(id="happy-hour-promo", href="/happy-hour")
    )
    featured: FeaturedProductsSection = Field(default_factory=FeaturedProductsSection)
    brands: BrandsSection = Field(default_factory=BrandsSection)
    about: AboutSection = Field(default_factory=AboutSection)
    support: SupportSection = Field(default_factory=SupportSection)
    seo: SeoSection = Field(default_factory=SeoSection)
    category_content: CategoryContentSection = Field(default_factory=CategoryContentSection)
    side_menu: SideMenuSection = Field(default_factory=SideMenuSection)
    header: HeaderSection = Field(default_factory=HeaderSection)
    footer: FooterSection = Field(default_factory=FooterSection)
    layout: List[LayoutBlock] = Field(default_factory=default_homepage_layout)
    """Extra section instances keyed by layout id (primary ids use typed fields)."""
    blocks: dict[str, Any] = Field(default_factory=dict)


class WebsiteHomepageRead(BaseModel):
    id: str
    company_id: str
    content: HomepageContent
    created_at: datetime
    updated_at: datetime


class WebsiteHomepageUpdate(BaseModel):
    content: Optional[HomepageContent] = None


class WebsiteHomepageResponse(BaseModel):
    data: WebsiteHomepageRead
    errors: List[str] = []


class StorefrontHomepageResponse(BaseModel):
    data: HomepageContent
    errors: List[str] = []
