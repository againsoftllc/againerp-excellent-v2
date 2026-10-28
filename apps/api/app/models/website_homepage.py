from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

DEFAULT_WEBSITE_HOMEPAGE_ID = "default"

DEFAULT_LAYOUT: list[dict[str, Any]] = [
    {"id": "hero", "type": "hero", "hidden": False},
    {"id": "categories", "type": "categories", "hidden": False},
    {"id": "banners", "type": "banners", "hidden": False},
    {"id": "featured", "type": "featured", "hidden": False},
    {"id": "brands", "type": "brands", "hidden": False},
    {"id": "about", "type": "about", "hidden": False},
    {"id": "support", "type": "support", "hidden": False},
]

DEFAULT_HERO: dict[str, Any] = {
    "autoplay_ms": 3000,
    "slides": [
        {
            "id": "s1",
            "image_url": "/images/image/cache/catalog/website/slider/slider-1880x1060.jpg",
            "href": "/offers",
            "alt": "Excellent Technology BD — HyperX Cloud II",
            "object_fit": "fill",
            "image_width": 1880,
            "image_height": 1060,
            "hidden": False,
        },
        {
            "id": "s2",
            "image_url": "/images/image/cache/catalog/website/slider/slider-1880x1060.jpg",
            "href": "/pc-builder",
            "alt": "Excellent Technology BD — Build Your Dream PC",
            "object_fit": "fill",
            "image_width": 1880,
            "image_height": 1060,
            "hidden": False,
        },
    ],
}

DEFAULT_CATEGORIES: dict[str, Any] = {
    "title": "Shop by Category",
    "subtitle": "Jump straight to the department you're after.",
    "hidden": False,
    "items": [],
}

DEFAULT_BANNERS: dict[str, Any] = {
    "slides": [
        {
            "id": "b1",
            "image_url": "/images/image/cache/catalog/website/banner/slider1-660x418.jpg",
            "href": "/ac",
            "alt": "Excellent Technology BD — Air Conditioner Offers",
            "object_fit": "fill",
            "image_width": 660,
            "image_height": 418,
            "hidden": False,
        },
        {
            "id": "b2",
            "image_url": "/images/image/cache/catalog/website/banner/slider2-660x418.jpg",
            "href": "/offers",
            "alt": "Excellent Technology BD — Hot Deals",
            "object_fit": "fill",
            "image_width": 660,
            "image_height": 418,
            "hidden": False,
        },
        {
            "id": "b3",
            "image_url": "/images/image/cache/catalog/website/banner/samrt-tv-exchange1-660x418.jpg",
            "href": "/tv",
            "alt": "Excellent Technology BD — Smart TV Exchange",
            "object_fit": "fill",
            "image_width": 660,
            "image_height": 418,
            "hidden": False,
        },
    ],
}

DEFAULT_HAPPY_HOUR_PROMO: dict[str, Any] = {
    "id": "happy-hour-promo",
    "image_url": "/images/banners/happy-hour-promo.jpg",
    "href": "/happy-hour",
    "alt": "Excellent Technology BD Happy Hour",
    "object_fit": "fill",
    "image_width": None,
    "image_height": None,
    "hidden": False,
}

DEFAULT_FEATURED: dict[str, Any] = {
    "title": "Most Wanted",
    "subtitle": "Explore Our Best-Selling Deal",
    # Product strip auto-scroll interval; 0 = off.
    "autoplay_ms": 0,
    "tabs": [
        {
            "id": "t1",
            "title": "Featured",
            "mode": "default",
            "default_source": "featured",
            "product_ids": [],
            "hidden": False,
        },
        {
            "id": "t2",
            "title": "New Arrivals",
            "mode": "default",
            "default_source": "newest",
            "product_ids": [],
            "hidden": False,
        },
        {
            "id": "t3",
            "title": "Best Sellers",
            "mode": "default",
            "default_source": "bestsellers",
            "product_ids": [],
            "hidden": False,
        },
    ],
}

DEFAULT_BRANDS: dict[str, Any] = {
    "title": "Brands We Distribute",
    "subtitle": "Official distributor of trusted brands.",
    # Brand strip auto-scroll interval; 0 = off.
    "autoplay_ms": 0,
    # Empty items = automatic active brands from catalog.
    "items": [],
}

DEFAULT_ABOUT_BODY_HTML = """<h3>Laptop, Desktop &amp; IT Shop in Dhaka</h3>
<p><a href="/">Excellent Technology BD</a> is a Dhaka-based IT retailer offering genuine laptops, desktops, monitors, components and accessories with official warranty — online and across our IDB Bhaban, Multiplan and Mirpur branches.</p>
<h3>Laptops, Desktops &amp; PC Builder</h3>
<p>From ASUS, Lenovo, HP, Dell, MSI and Apple laptops to custom gaming PCs, we cover every budget. Use our <a href="/pc-builder">PC Builder</a> to plan a compatible build online, or visit a branch for expert advice.</p>
<h3>Why Choose Excellent Technology BD?</h3>
<ul>
<li><strong>100% genuine products</strong> — with official brand warranty</li>
<li><strong>Three branches in Dhaka</strong> — test before you buy</li>
<li><strong>Easy EMI</strong> — 0% EMI on selected cards</li>
<li><strong>Fast delivery</strong> — same day inside Dhaka, nationwide courier</li>
</ul>
"""

DEFAULT_ABOUT: dict[str, Any] = {
    "title": "Excellent Technology BD",
    "subtitle": "A Trusted Computer Retailer & Online Shop in Bangladesh",
    # When true, body starts collapsed with expand/collapse control on storefront.
    "collapse_enabled": True,
    "body_html": DEFAULT_ABOUT_BODY_HTML,
}

_SUPPORT_IMG = "/images/image/cache/catalog/website/custom"

DEFAULT_SUPPORT: dict[str, Any] = {
    "title": "Support",
    "subtitle": "Official distributor of trusted brands.",
    "phone": "01913-004278",
    "phone_href": "tel:+8801913004278",
    "whatsapp": "01913-004278",
    "whatsapp_href": "https://wa.me/8801913004278",
    "hours": "10:00 AM - 08:00 PM",
    "phone_icon_url": f"{_SUPPORT_IMG}/support-phone-image-60x60.png",
    "agent_image_url": f"{_SUPPORT_IMG}/support-us-image-140x140.png",
    "store_label": "Store Locator",
    "store_title": "Find our Stores",
    "store_href": "/outlets",
    "store_icon_url": f"{_SUPPORT_IMG}/support-location-60x60.png",
}

_SIDE_IMG = "/uploads/media"

DEFAULT_SIDE_MENU: dict[str, Any] = {
    "enabled": True,
    "logo_url": "",
    "logo_href": "/",
    "items": [
        {
            "id": "sm1",
            "label": "Phone",
            "href": "#",
            "icon": "",
            "icon_url": f"{_SIDE_IMG}/sidemenu-phone-black-icon.svg",
            "active": False,
            "hidden": False,
        },
        {
            "id": "sm2",
            "label": "Message",
            "href": "#",
            "icon": "",
            "icon_url": f"{_SIDE_IMG}/sidemenu-message-icon.svg",
            "active": False,
            "hidden": False,
        },
        {
            "id": "sm3",
            "label": "Wishlist",
            "href": "/wishlist",
            "icon": "",
            "icon_url": f"{_SIDE_IMG}/sidemenu-wishlist-icon.svg",
            "active": False,
            "hidden": False,
        },
        {
            "id": "sm4",
            "label": "Gift",
            "href": "#",
            "icon": "",
            "icon_url": f"{_SIDE_IMG}/sidemenu-gift-black-icon.svg",
            "active": False,
            "hidden": False,
        },
        {
            "id": "sm5",
            "label": "Hot Deals",
            "href": "#",
            "icon": "",
            "icon_url": f"{_SIDE_IMG}/sidemenu-fire-black-icon.svg",
            "active": False,
            "hidden": False,
        },
        {
            "id": "sm6",
            "label": "PC Builder",
            "href": "/pc-builder",
            "icon": "",
            "icon_url": f"{_SIDE_IMG}/sidemenu-pc-icon.svg",
            "active": True,
            "hidden": False,
        },
    ],
}

_HEADER_IMG = "/uploads/media"

DEFAULT_HEADER_MOBILE: dict[str, Any] = {
    "enabled": True,
    "logo_url": "",
    "logo_href": "/",
    "search_placeholder": "Search Products",
}

DEFAULT_HEADER: dict[str, Any] = {
    "enabled": True,
    "logo_url": "",
    "logo_href": "/",
    "search_placeholder": "Search Products",
    "order_track": {
        "label": "Order Track",
        "href": "/order-track",
        "icon": "",
        "icon_url": f"{_HEADER_IMG}/header-order-track-icon.svg",
        "hidden": False,
    },
    "pc_builder": {
        "label": "PC Builder",
        "href": "/pc-builder",
        "icon": "",
        "icon_url": "",
        "hidden": False,
    },
    "mobile": dict(DEFAULT_HEADER_MOBILE),
}

_FOOTER_IMG = "/uploads/media"

DEFAULT_FOOTER_MOBILE: dict[str, Any] = {
    "enabled": True,
    "logo_url": "",
    "about_text": "",
    "hide_socials": False,
    "hide_membership": False,
    "hide_payment": False,
}

DEFAULT_FOOTER: dict[str, Any] = {
    "enabled": True,
    "logo_url": "",
    "about_text": (
        "Your trusted destination for laptops, desktops, components and IT accessories in "
        "Bangladesh — genuine products with official warranty."
    ),
    "socials": [
        {"id": "s1", "icon": "fa-facebook-f", "href": "#"},
        {"id": "s2", "icon": "fa-instagram", "href": "#"},
        {"id": "s3", "icon": "fa-whatsapp", "href": "https://wa.me/8801913004278"},
        {"id": "s4", "icon": "fa-youtube", "href": "#"},
    ],
    "links_title": "Important Links",
    "membership_title": "Membership",
    "membership_logo_url": f"{_FOOTER_IMG}/footer-partnership-logo.png",
    "head_office_text": (
        "IDB Branch: Shop# 315 (3rd Floor), BCS Computer City, IDB Bhaban, Agargaon, Dhaka-1207"
    ),
    "copyright_text": "© 2026, Excellent Technology BD, All Rights Reserved.",
    "payment_image_url": f"{_FOOTER_IMG}/footer-payment-partner.png",
    "mobile": dict(DEFAULT_FOOTER_MOBILE),
}


def featured_category_carousel_items(category_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same pick order as the storefront CategoryCarousel auto mode (top-menu roots + children)."""
    roots = [c for c in category_nodes if c.get("show_in_top_menu")]
    base = roots if roots else list(category_nodes)
    if len(base) >= 6:
        featured = base
    else:
        featured = list(base)
        for node in base:
            featured.extend(node.get("children") or [])
        featured = featured[:16]
    return [
        {
            "id": f"c{i + 1}",
            "category_id": str(node["id"]),
            "image_url": "",
            "href": "",
            "hidden": False,
        }
        for i, node in enumerate(featured)
        if node.get("id")
    ]


def categories_section_from_catalog(category_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": DEFAULT_CATEGORIES["title"],
        "subtitle": DEFAULT_CATEGORIES["subtitle"],
        "hidden": False,
        "items": featured_category_carousel_items(category_nodes),
    }


def brand_carousel_items(brands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pin active catalog brands for homepage brand strip."""
    return [
        {
            "id": f"br{i + 1}",
            "brand_id": str(row["id"]),
            "image_url": "",
            "href": "",
            "hidden": False,
        }
        for i, row in enumerate(brands)
        if row.get("id")
    ]


def brands_section_from_catalog(brands: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": DEFAULT_BRANDS["title"],
        "subtitle": DEFAULT_BRANDS["subtitle"],
        "autoplay_ms": DEFAULT_BRANDS["autoplay_ms"],
        "items": brand_carousel_items(brands),
    }


def dump_json(value: Any) -> str:
    return json.dumps(value if value is not None else {})


def load_json(value: Optional[str], default: Any = None) -> Any:
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default if default is not None else {}


class WebsiteHomepage(Base):
    """Singleton storefront homepage content (hero + future sections)."""

    __tablename__ = "website_homepage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=DEFAULT_WEBSITE_HOMEPAGE_ID)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    content_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
