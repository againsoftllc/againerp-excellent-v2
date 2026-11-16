"""Aladin catalog import — turn a product page URL into a real catalog product.

Wraps the existing URL → product pipeline (`app.services.catalog_ai`, already used by the
Catalog → Import → From URL admin page): fetch the page, extract structured product data
with an LLM, then create the product through the same code path `catalog_products.py` itself
uses (brand/category resolution, item identity, ecommerce mirror, default variant, image
import). Nothing new is invented here — this tool just gives that pipeline a chat front end.

Two-step like every other action tool:

1. **Preview** (`confirm` absent/false): fetch + extract, but create nothing. Shows the
   model what was found — name, price, brand/category (and whether each already exists or
   will be created new), images, specs, warnings — so the user can check it before anything
   is written.
2. **Execute** (`confirm=true`, only after the user agrees): re-runs the same extraction
   (the page is fetched fresh — cheap, and avoids trusting a stale draft from a separate
   request) and creates the product as a **draft**, auto-creating a missing brand and/or
   category exactly as the user asked ("category create kora na thakle category create korbe,
   brand na thakleo same").
"""

from __future__ import annotations

import json
import re
import time
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.auth_user import AuthUser
from app.schemas.catalog_ai_import import CatalogAiCreateRequest, CatalogAiExtractResponse
from app.services.ai.orchestrator import OrchestratorTool, RiskTier
from app.services.ai.providers.base import AIToolDefinition
from app.models.catalog_attribute_profile import CatalogAttributeProfile
from app.models.catalog_category import CatalogCategory
from app.models.catalog_product import CatalogProduct
from app.services.ai.image_service import find_product
from app.services.catalog_ai import seo_writer, spec_profile_service
from app.services.catalog_ai.importer_service import (
    normalize_warranty,
    _company_name,
    _sanitize_description,
    create_product_from_draft,
    extract_from_url,
)
from app.services.rbac import has_permission, is_system_manager

CONFIRM_NOTE = (
    "Nothing was created. Show this preview to the user and ask them to confirm; call again "
    "with confirm=true only after they explicitly agree."
)

# Extraction is a real network fetch + LLM call — non-deterministic, unlike a DB lookup.
# Re-running it on confirm could silently create a product that drifts from the preview the
# user actually approved (a field present in one extraction, blank in the next). Cache the
# extracted draft by URL for a short window so confirm reuses exactly what was shown; only
# falls back to a fresh extraction if the cache entry is gone (process restart, TTL expiry,
# or a different worker process — this cache is in-process only).
_EXTRACT_CACHE_TTL_SECONDS = 900
_extract_cache: dict[str, tuple[float, CatalogAiExtractResponse]] = {}
# Same idea for SEO fields written from an admin preset (LLM, non-deterministic): product id →
# the values shown in the preview, reused on confirm.
_seo_cache: dict[str, tuple[float, dict]] = {}
# add_product_specs: "<product id>|<profile name>" → the profile plan + mapped values shown in
# the preview (LLM mapping), reused on confirm.
_spec_cache: dict[str, tuple[float, dict]] = {}
# create_spec_profile_from_links: "<category url>|<product url>|<profile name>" → the proposal shown in the preview, reused on confirm.
_profile_link_cache: dict[str, tuple[float, dict]] = {}

def _cache_get(url: str) -> Optional[CatalogAiExtractResponse]:
    entry = _extract_cache.get(url)
    if not entry:
        return None
    cached_at, extracted = entry
    if time.time() - cached_at > _EXTRACT_CACHE_TTL_SECONDS:
        _extract_cache.pop(url, None)
        return None
    return extracted


def _cache_set(url: str, extracted: CatalogAiExtractResponse) -> None:
    # Bound the cache — this is a convenience for one URL reviewed then confirmed, not a store.
    if len(_extract_cache) > 200:
        _extract_cache.clear()
    _extract_cache[url] = (time.time(), extracted)


def _f(v: Optional[Decimal]) -> Optional[float]:
    return float(v) if v is not None else None


def _can_write_catalog(db: Session, user: Any) -> bool:
    if db is None or user is None:
        return False
    role = str(getattr(user, "role", "") or "").lower()
    if role in ("admin", "system_manager"):
        return True
    try:
        return is_system_manager(db, user) or has_permission(db, user, "catalog", "write")
    except Exception:
        return False


def _preview(db: Session, company_id: Optional[str], extracted: CatalogAiExtractResponse) -> dict:
    d = extracted.draft
    our_company = _company_name(db, company_id)
    description = _sanitize_description(d.description or d.short_description, seller_name=d.seller_site_name, source_url=d.source_url, our_company=our_company)
    warnings = list(extracted.warnings)
    # This exact URL was imported before — without this check, confirming silently creates a
    # second, near-identical product (verified live: it also broke add_product_seo's
    # name-based lookup afterward, "matches several products"). Surface it as a warning so the
    # model tells the user before they confirm, instead of finding out from a broken lookup later.
    existing = db.query(CatalogProduct).filter(CatalogProduct.source_url == d.source_url).first() if d.source_url else None
    if existing is not None:
        warnings.append(
            f"This exact URL was already imported as '{existing.name}' (SKU {existing.sku}, doc://product/{existing.id}). "
            "Confirming will create a SEPARATE duplicate product, not update the existing one — tell the user this and "
            "ask whether they really want a duplicate before calling confirm=true."
        )
    return {
        "action": "Import product from URL (draft)",
        "source_url": d.source_url,
        "name": d.name,
        "sku": d.sku or "(none on page — a short one will be generated)",
        "model": d.model,
        "price": _f(d.price),
        "currency": d.currency,
        "stock_status": "in_stock",
        "warranty": d.warranty,
        "origin": d.origin,
        "short_description": _sanitize_description(d.short_description, seller_name=d.seller_site_name, source_url=d.source_url, our_company=our_company),
        "description": description,
        "brand": {
            "name": d.brand_name,
            "status": "existing" if extracted.matched_brand_id else ("will be created" if d.brand_name else "not found on page"),
        },
        "category": {
            "name": d.category_name,
            "status": "existing" if extracted.matched_category_id else ("will be created" if d.category_name else "not found on page"),
        },
        "all_categories": [
            c.name
            for cid in extracted.matched_category_ids
            if (c := db.get(CatalogCategory, cid)) is not None
        ],
        "images_found": len(d.images),
        "sample_images": d.images[:3],
        "specifications": _spec_preview(db, extracted),
        "variants": [{"name": v.name, "attributes": v.attributes, "price": _f(v.price)} for v in d.variants] if d.variants else None,
        "product_type": "variable" if d.variants else "simple",
        "tags": d.tags,
        "warnings": warnings,
    }


def _spec_preview(db: Session, extracted: CatalogAiExtractResponse) -> dict:
    """What happens to the page's spec table on import: filled into the category's existing
    specification profile, or (no profile) kept as custom specs until the user approves a new one."""
    d = extracted.draft
    specs = spec_profile_service.specs_from_draft(d)
    count = spec_profile_service.spec_item_count(specs)
    if not count:
        return {"found_on_page": 0}
    names = [c.name for cid in extracted.matched_category_ids if (c := db.get(CatalogCategory, cid)) is not None]
    profile = spec_profile_service.find_profile(db, category_names=[*names, d.category_name or "", *d.category_names])
    chosen = (_overrides.get(d.source_url or "", {}) or {}).get("profile")  # named by the user in the chat
    if chosen == "none":
        return {
            "found_on_page": count,
            "groups": [g.group for g in d.specifications],
            "profile": None,
            "plan": "As you chose: no attribute profile - the specs stay on this product only.",
        }
    if chosen == "new":
        return {
            "found_on_page": count,
            "groups": [g.group for g in d.specifications],
            "profile": None,
            "plan": f"As you chose: a NEW attribute profile is created from the {count} attributes on the page.",
        }
    if chosen:
        picked = db.get(CatalogAttributeProfile, chosen)
        if picked is not None:
            profile = picked
    if profile is not None:
        return {
            "found_on_page": count,
            "groups": [g.group for g in d.specifications],
            "profile": profile.name,
            "plan": (
                f"Will be filled into the {'chosen' if chosen else 'existing'} '{profile.name}' attribute profile."
                + ("" if chosen else " To use a different profile, tell me its name.")
            ),
        }
    return {
        "found_on_page": count,
        "groups": [g.group for g in d.specifications],
        "profile": None,
        "plan": (
            f"No attribute profile matches '{d.category_name or 'this product'}'. Suggestion: create a new profile from the {count} "
            "attributes on the page. Or choose an existing attribute profile by telling me its name."
        ),
        "existing_profiles": [p.name for p in _all_profiles(db)][:30],
    }


def _category_chain(db: Session, category_id: str) -> str:
    names: list[str] = []
    node, seen = db.get(CatalogCategory, category_id), set()
    while node is not None and node.id not in seen:
        seen.add(node.id)
        names.append(node.name)
        node = db.get(CatalogCategory, node.parent_id) if node.parent_id else None
    return " > ".join(reversed(names))


def _fill_preview_md(db: Session, company_id: Optional[str], row: CatalogProduct, extracted: CatalogAiExtractResponse) -> str:
    """The review sheet shown BEFORE anything is written to a draft: what the AI collected from the source page and which
    category / brand / specification profile it will be connected to (and which of those would be created new)."""
    d = extracted.draft
    our_company = _company_name(db, company_id)
    clean = lambda t: _sanitize_description(t, seller_name=d.seller_site_name, source_url=d.source_url, our_company=our_company)  # noqa: E731
    specs = spec_profile_service.specs_from_draft(d)
    n_specs = spec_profile_service.spec_item_count(specs)
    cat_names = [c.name for cid in extracted.matched_category_ids if (c := db.get(CatalogCategory, cid)) is not None]
    profile = spec_profile_service.find_profile(db, category_names=[*cat_names, d.category_name or "", *d.category_names]) if n_specs else None

    if extracted.matched_category_id:
        category = f"{_category_chain(db, extracted.matched_category_id)} — existing"
    elif d.category_name:
        category = f"{d.category_name} — **NEW, will be created** (needs your approval)"
    else:
        category = "not found on the page"
    others = [n for n in cat_names[1:]]
    if extracted.matched_brand_id:
        brand = f"{d.brand_name} — existing"
    elif d.brand_name:
        brand = f"{d.brand_name} — **NEW, will be created** (needs your approval)"
    else:
        brand = "not found on the page"
    if not n_specs:
        spec = "no specification table found on the page"
    elif profile is not None:
        spec = f"{n_specs} attributes from the source → connected to the existing **{profile.name}** profile"
        unmatched = spec_profile_service.unmatched_filters(spec_profile_service.profile_fields(db, profile.id), d.source_filters or [])
        if unmatched:
            spec += (
                f"\n  - **{len(unmatched)} source filter(s) have no attribute in this profile** → will be added to its "
                f"**{spec_profile_service.KEY_FEATURE_GROUP}** group (multi-select) and filled for this product (needs your approval): "
                + ", ".join(f"{u['title']} ({len(u['options'])} options)" for u in unmatched)
            )
    else:
        n_flt = len(d.source_filters or [])
        spec = (
            f"{n_specs} attributes from the source → no profile for this category yet: **NEW profile "
            f"'{d.category_name or row.category or 'General'}' will be created** from them"
            + (f" with {n_flt} filters from the source shop (those no attribute names go to a '{spec_profile_service.KEY_FEATURE_GROUP}' group)" if n_flt else "")
            + " (needs your approval)"
        )
    desc = (clean(d.description or "") or "").strip()
    words = len(desc.split())
    short = [ln.strip(" -•\t") for ln in (clean(d.short_description or "") or "").splitlines() if ln.strip()]
    lines = [
        f"### Review before updating `{row.name}`",
        f"- **Title:** {row.name}  →  **{d.name}**" if d.name.strip() != (row.name or "").strip() else f"- **Title:** {d.name} (unchanged)",
        f"- **Category:** {category}" + (f"  (also filed under: {', '.join(others)})" if others else ""),
        f"- **Brand:** {brand}",
        f"- **Specification profile:** {spec}",
        f"- **Price:** {_f(d.price) if d.price else 'not found'}"
        + (f"  (old price {_f(d.compare_at_price)})" if d.compare_at_price else "")
        + f"  ·  **Stock status:** {d.stock_status or 'in_stock'}",
        f"- **Warranty:** {d.warranty or '—'}  ·  **Origin:** {d.origin or '—'}",
        f"- **Images:** {len(d.images)} found",
        f"- **Tags:** {', '.join(d.tags) if d.tags else '—'}",
        f"- **SEO:** {d.seo_title or '—'}",
    ]
    if short:
        lines.append("- **Short description:**")
        lines += [f"  - {s}" for s in short[:6]]
    if desc:
        lines.append(f"- **Description:** {words} words — “{desc[:280]}{'…' if len(desc) > 280 else ''}”")
    if d.variants:
        lines.append(f"- **Variants:** {len(d.variants)}")
    for w in extracted.warnings:
        lines.append(f"- ⚠️ {w}")
    lines.append("\nNothing is saved yet. The product stays a **draft**; its slug and SKU do not change.")
    return "\n".join(lines)


def fill_review(db: Session, company_id: Optional[str], row: CatalogProduct, extracted: CatalogAiExtractResponse) -> dict:
    """The structured review the product drawer shows (as a card, not text) BEFORE a draft is filled from its source:
    the scraped data plus what the AI selected for category / brand / specification profile - the admin can change those
    three in the card, then approve."""
    d = extracted.draft
    our_company = _company_name(db, company_id)
    clean = lambda t: _sanitize_description(t, seller_name=d.seller_site_name, source_url=d.source_url, our_company=our_company)  # noqa: E731
    specs = spec_profile_service.specs_from_draft(d)
    n_specs = spec_profile_service.spec_item_count(specs)
    cat_names = [c.name for cid in extracted.matched_category_ids if (c := db.get(CatalogCategory, cid)) is not None]
    profile = spec_profile_service.find_profile(db, category_names=[*cat_names, d.category_name or "", *d.category_names]) if n_specs else None
    # the profile the user named in the chat (or "new" / "none") replaces the AI's own pick
    chosen = (_overrides.get(d.source_url or "", {}) or {}).get("profile")
    forced: Optional[str] = None
    if chosen == "none":
        profile, forced = None, "none"
    elif chosen == "new":
        profile, forced = None, "new"
    elif chosen:
        picked = db.get(CatalogAttributeProfile, chosen)
        if picked is not None:
            profile = picked
    unmatched = (
        spec_profile_service.unmatched_filters(spec_profile_service.profile_fields(db, profile.id), d.source_filters or [])
        if profile is not None else []
    )
    where = d.category_name or (cat_names[0] if cat_names else "") or "this category"
    suggestion = None
    if profile is None and not forced:
        suggestion = (
            f"No attribute profile matches '{where}'. Suggestion: create a new profile from the {n_specs} attributes on the source page. "
            "Or pick an existing attribute profile from the dropdown (or tell me its name)."
            if n_specs
            else "No specification table was found on the source page, so there is nothing to put in a profile."
        )
    desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", clean(d.description or "") or "")).strip()  # plain text, no tags
    short = [ln.strip(" -•\t") for ln in (clean(d.short_description or "") or "").splitlines() if ln.strip(" -•\t")]
    return {
        "overrides": dict(_overrides.get(d.source_url or "", {})),  # values the admin set in the chat
        "product": {"id": row.id, "name": row.name, "source_url": d.source_url},
        "title": {"current": row.name, "new": d.name},
        "images": list(d.images[:20]),
        "price": _f(d.price),
        "compare_at_price": _f(d.compare_at_price),  # the source's old price -> the product's Compare-at price
        "stock_status": d.stock_status or "in_stock",
        "warranty": d.warranty,
        "origin": d.origin,
        "brand": {"name": d.brand_name, "matched_id": extracted.matched_brand_id},
        "categories": {
            "name": d.category_name,
            "matched_ids": list(extracted.matched_category_ids),  # primary first, then its parents
            "is_new": bool(d.category_name and not extracted.matched_category_id),
            "new_level": next((w for w in extracted.warnings if w.startswith("Category '") and "will be created under" in w), None),
        },
        "profile": {
            "status": "existing" if profile is not None else (forced or ("new" if n_specs else "none")),
            "matched_id": profile.id if profile is not None else None,
            "matched_name": profile.name if profile is not None else None,
            "chosen_by_user": bool(chosen and (profile is not None or forced)),
            "suggestion": suggestion,
            "attributes": n_specs,
            "source_filters": len(d.source_filters or []),
            "key_feature_filters": [u["title"] for u in unmatched],
        },
        "tags": list(d.tags),
        "short_description": short[:6],
        "description_words": len(desc.split()),
        "description_excerpt": desc[:400],
        "warnings": list(extracted.warnings),
    }


def apply_fill(
    db: Session,
    user: Any,
    company_id: Optional[str],
    row: CatalogProduct,
    extracted: CatalogAiExtractResponse,
    *,
    brand_id: Optional[str] = None,
    category_ids: Optional[list[str]] = None,
    profile_id: Optional[str] = None,
) -> CatalogProduct:
    """Fill the draft from the extracted source data - the AI's choices, or the admin's own (`brand_id`, `category_ids`
    first = primary, `profile_id` = an existing profile id / "new" / "none") from the review card. Raises HTTPException."""
    d = extracted.draft
    cat_ids = [c for c in (category_ids or []) if c]
    has_specs = bool(spec_profile_service.spec_item_count(spec_profile_service.specs_from_draft(d)))
    cat_for_profile = d.category_name or row.category
    needs_profile = bool(
        has_specs and cat_for_profile and spec_profile_service.find_profile(db, category_names=[cat_for_profile]) is None
    )
    payload = CatalogAiCreateRequest(
        draft=d,
        brand_id=brand_id or extracted.matched_brand_id,
        category_id=(cat_ids[0] if cat_ids else extracted.matched_category_id),
        category_ids=cat_ids or extracted.matched_category_ids,
        create_brand_if_missing=not brand_id,
        # the admin left the AI's category pick alone -> a missing deeper level of the source's breadcrumb is created under it
        create_category_if_missing=(not cat_ids) or cat_ids == list(extracted.matched_category_ids),
        import_images=True,
        status=row.status if row.status in ("draft", "published", "unlisted") else "draft",
    )
    row = create_product_from_draft(
        db, payload, user, existing=row, create_spec_profile=needs_profile or profile_id == "new",
        update_name=True, extend_spec_profile=True, spec_profile_id=profile_id or None,
    )
    try:
        from app.services.plugins import price_update_service as pus

        pus.ensure_source_site(db, company_id)  # type: ignore[arg-type]
        pus.refresh_product_competitor(
            db, company_id=company_id, product=row, competitor=pus.SOURCE_ID,  # type: ignore[arg-type]
            settings=pus.get_or_create_settings(db, company_id), allow_ai=False,  # type: ignore[arg-type]
        )
    except Exception:  # noqa: BLE001
        db.rollback()
    return row


# What the admin said in the chat while a review was open ("price 130000"): kept per source URL and laid over the
# extraction every time it is shown or applied, so a later message adds to the earlier context instead of replacing it.
_OVERRIDABLE = ("price", "compare_at_price", "name", "model", "warranty", "origin", "stock_status", "profile")
_overrides: dict[str, dict] = {}

# --- the specification profile the user names in the chat ("laptop attribute profile use koro") -------------------------------
# The review card has a dropdown of every profile; these let the user do the same in words: the name is matched to an existing
# profile (or "new" = create one from the source, "none" = keep the specs on the product only) and laid over the review.
_PROFILE_FILLER = {
    "attribute", "attributes", "specification", "specifications", "spec", "specs", "profile", "profiles", "use", "koro", "kore",
    "dao", "select", "choose", "the", "a", "an", "er", "ta", "ti", "ke", "diye", "niye", "ei", "this", "that", "please",
}


def _profile_tokens(text: str) -> list[str]:
    out: list[str] = []
    for word in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if word in _PROFILE_FILLER:
            continue
        out.append(word[:-1] if len(word) > 3 and word.endswith("s") else word)  # Laptops = Laptop
    return out


def match_profile_choice(profiles: list[tuple[str, str]], text: str) -> Optional[str]:
    """A profile id, "new" or "none" for what the user wrote - or None when no single profile fits it.
    `profiles` = [(id, name)]. Same words in any order beat 'contains all the words'; a tie is not guessed."""
    raw = (text or "").strip()
    low = raw.lower()
    if low in {"new", "create", "create new", "new profile", "create a new profile", "notun"}:
        return "new"
    if low in {"none", "no profile", "no", "skip"}:
        return "none"
    for pid, _name in profiles:
        if raw == pid:
            return pid
    tokens = _profile_tokens(raw)
    if not tokens:
        return None
    want = set(tokens)
    named = [(pid, set(_profile_tokens(name))) for pid, name in profiles]
    exact = [pid for pid, words in named if words == want]
    if exact:
        return exact[0]
    containing = [(pid, words) for pid, words in named if want <= words]
    if len(containing) == 1:
        return containing[0][0]
    if containing:
        fewest = min(len(words) for _pid, words in containing)
        best = [pid for pid, words in containing if len(words) == fewest]
        return best[0] if len(best) == 1 else None
    return None


def _all_profiles(db: Session) -> list[CatalogAttributeProfile]:
    return (
        db.query(CatalogAttributeProfile)
        .filter(CatalogAttributeProfile.is_active.is_(True))
        .order_by(CatalogAttributeProfile.sort_order.asc(), CatalogAttributeProfile.name.asc())
        .all()
    )


def resolve_profile_choice(db: Session, text: str) -> tuple[Optional[str], list[str]]:
    """(profile id | "new" | "none" | None, the names of every profile)."""
    profiles = _all_profiles(db)
    return match_profile_choice([(p.id, p.name) for p in profiles], text), [p.name for p in profiles]


def _profile_name(db: Session, choice: Optional[str]) -> Optional[str]:
    if not choice or choice in ("new", "none"):
        return None
    p = db.get(CatalogAttributeProfile, choice)
    return p.name if p is not None else None


def _apply_overrides(extracted: CatalogAiExtractResponse, ov: dict) -> CatalogAiExtractResponse:
    upd: dict = {}
    for k, v in (ov or {}).items():
        if k in ("price", "compare_at_price"):
            try:
                upd[k] = Decimal(str(v).replace(",", "").strip())
            except Exception:  # noqa: BLE001
                continue
        elif k == "warranty":
            upd[k] = normalize_warranty(str(v)) or str(v).strip()[:200]
        elif k == "stock_status":
            if str(v) in ("in_stock", "out_of_stock", "pre_order", "coming_soon"):
                upd[k] = str(v)
        elif k in ("name", "model", "origin") and str(v).strip():
            upd[k] = str(v).strip()[:255]
    if not upd:
        return extracted
    return extracted.model_copy(update={"draft": extracted.draft.model_copy(update=upd)})


def get_extracted(db: Session, company_id: Optional[str], url: str) -> CatalogAiExtractResponse:
    """The extraction the review showed (cached 15 min), else a fresh one - with the admin's chat overrides laid over it."""
    cached = _cache_get(url)
    if cached is None:
        cached = extract_from_url(db, url, company_id=company_id)  # type: ignore[arg-type]
        db.rollback()
    return _apply_overrides(cached, _overrides.get(url, {}))


def drop_extracted(url: str) -> None:
    _extract_cache.pop(url, None)
    _overrides.pop(url, None)


def _profile_line(profile: dict) -> str:
    """What the assistant's reply must say about the specification profile of a review (the card has the dropdown)."""
    name = profile.get("matched_name")
    status = profile.get("status")
    if profile.get("chosen_by_user"):
        if status == "existing" and name:
            return f"The user chose the '{name}' attribute profile - say that it is selected in the card."
        if status == "new":
            return "The user chose to create a NEW attribute profile from the source - say that it is selected in the card."
        return "The user chose to keep the specifications on the product only (no profile) - say that it is selected in the card."
    if status == "existing" and name:
        return (
            f"Say which attribute profile the AI connected: '{name}'. They can change it with the 'Specification profile' dropdown "
            "in the card, or tell you another profile's name."
        )
    if status == "new":
        return (
            "There is NO attribute profile for this category: say so, SUGGEST creating a new profile from the source (it is "
            "pre-selected in the card), and say that instead they can pick an existing attribute profile from the 'Specification "
            "profile' dropdown in the card or tell you its name (you can list them with list_spec_profiles)."
        )
    return "The source page has no specification table, so no attribute profile is used."


def build_catalog_import_tools(*, db: Session | None, company_id: str | None, user: Any | None) -> list[OrchestratorTool]:
    def import_product_from_url(inp: dict) -> dict:
        if not _can_write_catalog(db, user):
            return {"error": "Importing products needs catalog write permission."}
        url = str(inp.get("url") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return {"error": "A full product page URL (starting with http:// or https://) is required."}

        confirming = bool(inp.get("confirm"))
        said_profile = str(inp.get("profile") or "").strip()
        if said_profile:
            # the user named an attribute profile in the chat: an existing one (by name), "new" or "none"
            choice, names = resolve_profile_choice(db, said_profile)  # type: ignore[arg-type]
            if choice is None:
                return {
                    "error": f"No single attribute profile matches '{said_profile}'.",
                    "profiles": names[:60],
                    "note": "Tell the user in one line that no profile has that name, list the closest names from 'profiles', and ask which one to use - or whether to create a new one from the page.",
                }
            _overrides[url] = {**_overrides.get(url, {}), "profile": choice}
        extracted = _cache_get(url) if (confirming or said_profile) else None
        if extracted is None:
            try:
                extracted = extract_from_url(db, url, company_id=company_id)  # type: ignore[arg-type]
            except HTTPException as exc:
                db.rollback()  # type: ignore[union-attr]
                return {"error": exc.detail}
            except Exception as exc:  # noqa: BLE001 — network/parse failures should not crash the turn
                db.rollback()  # type: ignore[union-attr]
                return {"error": f"Could not read that page: {exc}"}

            if not extracted.draft.name.strip():
                return {"error": "Could not find a product name on that page — it may not be a product page, or the layout is unsupported.", "warnings": extracted.warnings}

        if not confirming:
            preview = _preview(db, company_id, extracted)  # type: ignore[arg-type]
            _cache_set(url, extracted)
            return {
                "status": "preview",
                "preview": preview,
                "note": CONFIRM_NOTE + " ATTRIBUTE PROFILE: say in the same message which attribute profile the preview connects (specifications.plan). If none fits (specifications.existing_profiles), SUGGEST creating a new one from the page and tell the user they can instead choose an existing profile by name - when they name one, call this tool again with the same url and profile=<name> (still without confirm).",
            }

        payload = CatalogAiCreateRequest(
            draft=extracted.draft,
            brand_id=extracted.matched_brand_id,
            category_id=extracted.matched_category_id,
            category_ids=extracted.matched_category_ids,
            create_brand_if_missing=True,
            create_category_if_missing=True,
            import_images=True,
            status="draft",
        )
        _extract_cache.pop(url, None)
        chosen_profile = _overrides.pop(url, {}).get("profile")  # what the user named in the chat goes with the product
        try:
            row = create_product_from_draft(
                db, payload, user,  # type: ignore[arg-type]
                create_spec_profile=(chosen_profile == "new"), spec_profile_id=chosen_profile or None,
            )
        except HTTPException as exc:
            db.rollback()  # type: ignore[union-attr] — undo any partial flush (e.g. a resolved/created brand or category) before the gateway's own end-of-turn commit would otherwise persist it
            return {"error": exc.detail}
        except Exception as exc:  # noqa: BLE001
            db.rollback()  # type: ignore[union-attr]
            return {"error": f"Could not create the product: {exc}"}

        specs_info = _spec_result(row, extracted)
        return {
            "status": "created",
            "document": "Product",
            "id": row.id,
            "sku": row.sku,
            "name": row.name,
            "model": row.model,
            "origin": row.origin,
            "product_status": row.status,
            "product_type": row.product_type,
            "variant_count": len(extracted.draft.variants),
            "brand_created": bool(extracted.draft.brand_name and not extracted.matched_brand_id),
            "category_created": bool(extracted.draft.category_name and not extracted.matched_category_id),
            "images_imported": len(extracted.draft.images[:8]),
            "doc_link": f"doc://product/{row.id}",
            "path": f"/website/products?edit={row.id}",
            "specifications": specs_info,
            "seo": {"focus_keyphrase": row.focus_keyphrase, "meta_title": row.seo_title, "meta_description": row.seo_description},
            "note": (
                "Created as a draft — publish it from the product page once reviewed. "
                + (
                    "No specification profile exists for this product's category: first ask the user in plain text "
                    "(no tool call) whether to create one from the page's specs — if yes, call add_product_specs "
                    "(preview first). Then ask "
                    if specs_info.get("needs_profile")
                    else (
                        "Some storefront filter fields are still empty (specifications.filters_not_set) — tell the "
                        "user and offer add_product_specs to fill them (it can propose new filter options). Then ask "
                        if specs_info.get("filters_not_set")
                        else "Now ask "
                    )
                )
                + "the user in plain text (no tool call) whether anything else needs changing. SEO (Focus "
                "Keyphrase, Meta title, Meta description) was already written on import — show it (result 'seo'); "
                "only call add_product_seo if the user wants it rewritten."
            ),
        }

    def create_spec_profile_from_links(inp: dict) -> dict:
        """A specification profile from TWO links: the source shop's category page (its storefront filters) and one product
        page of that category (its spec table). No product is created - only the profile."""
        if not _can_write_catalog(db, user):
            return {"error": "Creating a specification profile needs catalog write permission."}
        category_url = str(inp.get("category_url") or "").strip()
        product_url = str(inp.get("product_url") or "").strip()
        for label, u in (("category_url", category_url), ("product_url", product_url)):
            if not u.lower().startswith(("http://", "https://")):
                return {"error": f"{label} must be a full link starting with http:// or https://. A profile needs one category page link (for the filters) and one product page link (for the specifications)."}
        if category_url.rstrip("/") == product_url.rstrip("/"):
            return {"error": "Those two links are the same page. Give the category (listing) page AND one product page of that category."}
        name = re.sub(r"\s+", " ", str(inp.get("profile_name") or "")).strip()[:255]
        confirming = bool(inp.get("confirm"))
        key = f"{category_url}|{product_url}|{name.lower()}"
        entry = _profile_link_cache.get(key) if confirming else None
        plan = entry[1] if entry and time.time() - entry[0] <= _EXTRACT_CACHE_TTL_SECONDS else None
        if plan is None:
            extracted = _cache_get(product_url)
            if extracted is None:
                try:
                    extracted = extract_from_url(db, product_url, company_id=company_id)  # type: ignore[arg-type]
                except HTTPException as exc:
                    db.rollback()  # type: ignore[union-attr]
                    return {"error": exc.detail}
                except Exception as exc:  # noqa: BLE001
                    db.rollback()  # type: ignore[union-attr]
                    return {"error": f"Could not read the product page: {exc}"}
                _cache_set(product_url, extracted)
            d = extracted.draft
            specs = spec_profile_service.specs_from_draft(d)
            if not spec_profile_service.spec_item_count(specs):
                return {"error": "No specification table was found on the product page - give a product page (not a category page) that lists its specifications."}
            from app.services.catalog_ai.scraper import fetch_category_filters

            filters = fetch_category_filters(category_url)
            name = name or (d.category_name or "").strip() or "General"
            exists = db.query(CatalogAttributeProfile).filter(CatalogAttributeProfile.name.ilike(name)).first()  # type: ignore[union-attr]
            if exists is not None:
                return {"error": f"A specification profile named '{exists.name}' already exists. Pick another name, or use it as it is."}
            proposal = spec_profile_service.attach_source_filters(
                spec_profile_service.propose_profile(name, specs), specs, filters, db=db, company_id=company_id  # type: ignore[arg-type]
            )
            if not proposal["groups"]:
                return {"error": "The product page's specification table was empty - nothing to build a profile from."}
            warnings = []
            if not filters:
                warnings.append("No filters could be read from the category page (the shop may block the server or the link is not a category listing) - the profile will have no storefront filters.")
            plan = {"proposal": proposal, "labels": [d.category_name] if d.category_name else [], "warnings": warnings, "product": d.name}
            if len(_profile_link_cache) > 50:
                _profile_link_cache.clear()
            _profile_link_cache[key] = (time.time(), plan)
        proposal = plan["proposal"]
        filters_out = [
            {
                "filter": e["title"],
                "on_attribute": f"{e['group']} > {e['attribute']}" + (" (new attribute)" if e["new"] else ""),
                "type": e["kind"],
                "options": len(e["options"]),
                "sample": e["options"][:5],
            }
            for e in (proposal.get("filter_attrs") or [])
        ]
        if not confirming:
            return {
                "status": "preview",
                "preview": {
                    "action": "Create specification profile (no product is created)",
                    "profile_name": proposal["name"],
                    "applies_to_categories": plan["labels"] or ["(set later in Website → Specifications)"],
                    "groups": {g["name"]: len(g["attributes"]) for g in proposal["groups"]},
                    "fields": sum(len(g["attributes"]) for g in proposal["groups"]),
                    "storefront_filters": filters_out,
                    "spec_source": plan["product"],
                    "warnings": plan["warnings"],
                },
                "note": CONFIRM_NOTE
                + " Show the groups and ALL storefront_filters (filter, the attribute it sits on, type, option count). Say which link the specs came from and which the filters.",
            }
        try:
            profile = spec_profile_service.create_profile(
                db,  # type: ignore[arg-type]
                company_id=company_id or "default",
                proposal=proposal,
                category_labels=plan["labels"],
            )
        except HTTPException as exc:
            db.rollback()  # type: ignore[union-attr]
            return {"error": exc.detail}
        db.commit()  # type: ignore[union-attr]
        _profile_link_cache.pop(key, None)
        return {
            "status": "created",
            "document": "Specification profile",
            "id": profile.id,
            "name": profile.name,
            "groups": len(proposal["groups"]),
            "fields": sum(len(g["attributes"]) for g in proposal["groups"]),
            "storefront_filters": filters_out,
            "path": f"/website/attributes?view={profile.id}",
            "open_link": f"[Open in Attributes](/website/attributes?view={profile.id})",
            "note": "Show the link EXACTLY as open_link (a path on this admin - never put a website domain such as the source shop's in front of it). The profile exists now. Products pick it up through their category; a product's filter values are filled when its specifications are added (add_product_specs / fill_product_from_source).",
        }

    def _spec_result(row: CatalogProduct, extracted: CatalogAiExtractResponse) -> dict:
        count = spec_profile_service.spec_item_count(spec_profile_service.specs_from_draft(extracted.draft))
        if not count:
            return {"found_on_page": 0}
        if row.attribute_profile_id:
            profile = db.get(CatalogAttributeProfile, row.attribute_profile_id)  # type: ignore[union-attr]
            gaps = spec_profile_service.filter_gaps(db, row)  # type: ignore[arg-type]
            return {
                "found_on_page": count,
                "profile": profile.name if profile else None,
                "fields_filled": spec_profile_service.filled_count(db, row.id),  # type: ignore[arg-type]
                "filters_not_set": gaps or None,
            }
        return {"found_on_page": count, "profile": None, "saved_as": "custom specs", "needs_profile": True}

    def _resolve_product(ref: str) -> dict:
        found = find_product(db, company_id, ref) if db is not None else None
        if found is None:
            return {"error": f"No product matches '{ref}'."}
        if isinstance(found, list):
            return {"error": f"'{ref}' matches several products — ask the user which one.", "candidates": [{"id": p.id, "name": p.name, "sku": p.sku} for p in found]}
        return {"ok": found}

    def _preset_seo(product: CatalogProduct) -> dict:
        """seo_writer.write_seo, cached per product for the confirm window so the values saved
        on confirm are exactly the ones the user was shown in the preview."""
        cached = _seo_cache.get(product.id)
        if cached and time.time() - cached[0] <= _EXTRACT_CACHE_TTL_SECONDS:
            return cached[1]
        written = seo_writer.write_seo(db, company_id, product)  # type: ignore[arg-type]
        if written:
            if len(_seo_cache) > 200:
                _seo_cache.clear()
            _seo_cache[product.id] = (time.time(), written)
        return written

    def add_product_seo(inp: dict) -> dict:
        if not _can_write_catalog(db, user):
            return {"error": "Updating SEO fields needs catalog write permission."}
        res = _resolve_product(str(inp.get("product") or ""))
        if "ok" not in res:
            return res
        product: CatalogProduct = res["ok"]
        given = {k: str(inp.get(k) or "").strip() for k in ("focus_keyphrase", "meta_title", "meta_description")}
        written = {} if all(given.values()) else _preset_seo(product)
        fallback = seo_writer.default_seo(db, company_id, product)  # type: ignore[arg-type]
        focus_keyphrase = given["focus_keyphrase"] or written.get("focus_keyphrase") or fallback["focus_keyphrase"]
        meta_title = given["meta_title"] or written.get("meta_title") or fallback["meta_title"]
        meta_description = given["meta_description"] or written.get("meta_description") or fallback["meta_description"]
        fixed = seo_writer.enforce_checklist(
            product, {"focus_keyphrase": focus_keyphrase, "meta_title": meta_title, "meta_description": meta_description}, touch_description=False
        )  # the SEO checklist (docs/AI/product-upload.md A13); what the user typed exactly is kept
        focus_keyphrase = given["focus_keyphrase"] or fixed["focus_keyphrase"]
        meta_title = given["meta_title"] or fixed["meta_title"]
        meta_description = given["meta_description"] or fixed["meta_description"]
        summary = {
            "action": "Set SEO fields",
            "product": {"id": product.id, "name": product.name},
            "focus_keyphrase": focus_keyphrase,
            "meta_title": meta_title,
            "meta_description": meta_description,
        }
        if not inp.get("confirm"):
            return {"status": "preview", "preview": summary, "note": CONFIRM_NOTE}
        _seo_cache.pop(product.id, None)
        was = {"focus_keyphrase": product.focus_keyphrase, "meta_title": product.seo_title, "meta_description": product.seo_description}
        product.focus_keyphrase = focus_keyphrase[:200]
        product.seo_title = meta_title[:255]
        product.seo_description = meta_description
        db.commit()  # type: ignore[union-attr]
        return {
            "status": "updated",
            "document": "Product SEO",
            "id": product.id,
            "name": product.name,
            "focus_keyphrase": product.focus_keyphrase,
            "meta_title": product.seo_title,
            "meta_description": product.seo_description,
            "before": was,
            "after": {"focus_keyphrase": product.focus_keyphrase, "meta_title": product.seo_title, "meta_description": product.seo_description},
            "doc_link": f"doc://product/{product.id}",
            "path": f"/website/products?edit={product.id}",
        }

    def _source_specs(product: CatalogProduct) -> list[dict]:
        specs = spec_profile_service.specs_from_product(product)
        if specs or not product.source_url:
            return specs
        # Older product without stored custom specs: read them from its source page again.
        extracted = _cache_get(product.source_url)
        if extracted is None:
            try:
                extracted = extract_from_url(db, product.source_url, company_id=company_id)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                db.rollback()  # type: ignore[union-attr]
                return []
            _cache_set(product.source_url, extracted)
        return spec_profile_service.specs_from_draft(extracted.draft)

    def _source_filters(product: CatalogProduct) -> list[dict]:
        """The source shop's storefront filters for this product's category (its breadcrumb's category pages) - the new profile's Overview."""
        if not product.source_url:
            return []
        extracted = _cache_get(product.source_url)
        if extracted is None:
            try:
                extracted = extract_from_url(db, product.source_url, company_id=company_id)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                db.rollback()  # type: ignore[union-attr]
                return []
            _cache_set(product.source_url, extracted)
        return list(extracted.draft.source_filters or [])

    def _spec_key(product: CatalogProduct, profile_name: str) -> str:
        # profile_name only matters when a new profile would be created — models add or drop it
        # freely between preview and confirm, which must not force a fresh (LLM) mapping.
        if spec_profile_service.find_profile(db, product=product) is not None:  # type: ignore[arg-type]
            return f"{product.id}|"
        return f"{product.id}|{profile_name.strip().lower()}"

    def _spec_plan(product: CatalogProduct, profile_name: str) -> dict:
        """Profile (existing or proposed) + mapped values — cached per product for the confirm
        window so confirm saves exactly what the preview showed (the mapping uses an LLM)."""
        key = _spec_key(product, profile_name)
        cached = _spec_cache.get(key)
        if cached and time.time() - cached[0] <= _EXTRACT_CACHE_TTL_SECONDS:
            return cached[1]
        specs = _source_specs(product)
        if not spec_profile_service.spec_item_count(specs):
            return {"error": "This product has no source specifications to add (no imported spec table and no source page)."}
        profile = spec_profile_service.find_profile(db, product=product)  # type: ignore[arg-type]
        if profile is not None:
            fields = spec_profile_service.profile_fields(db, profile.id)  # type: ignore[arg-type]
            values, off = spec_profile_service.map_values_detailed(db, company_id, specs, fields)  # type: ignore[arg-type]
            plan = {"profile_id": profile.id, "profile": profile.name, "fields": fields, "values": values, "off": off}
        else:
            name = profile_name.strip() or product.category or "General"
            proposal = spec_profile_service.attach_source_filters(
                spec_profile_service.propose_profile(name, specs), specs, _source_filters(product), db=db, company_id=company_id  # type: ignore[arg-type]
            )
            if not proposal["groups"]:
                return {"error": "The source specifications are empty — nothing to build a profile from."}
            plan = {"profile_id": None, "proposal": proposal, "specs": specs}
        if len(_spec_cache) > 200:
            _spec_cache.clear()
        _spec_cache[key] = (time.time(), plan)
        return plan

    def add_product_specs(inp: dict) -> dict:
        if not _can_write_catalog(db, user):
            return {"error": "Adding specifications needs catalog write permission."}
        res = _resolve_product(str(inp.get("product") or ""))
        if "ok" not in res:
            return res
        product: CatalogProduct = res["ok"]
        profile_name = str(inp.get("profile_name") or "")
        plan = _spec_plan(product, profile_name)
        if "error" in plan:
            return plan
        key = _spec_key(product, profile_name)

        if plan["profile_id"]:
            names = {f["id"]: f"{f['group']} > {f['name']}" for f in plan["fields"]}
            # Fields that already have a value keep it (fill_product never overwrites), so the
            # preview must show those as they are — not a source value that would not be saved.
            existing = spec_profile_service.current_values(db, product.id)  # type: ignore[arg-type]
            new_values = {k: v for k, v in plan["values"].items() if k not in existing}
            off = {k: v for k, v in (plan.get("off") or {}).items() if k not in existing}
            add_options = bool(inp.get("add_missing_options")) and bool(off)
            filters = spec_profile_service.filter_report(plan["fields"], {**existing, **new_values}, off)
            values = {**new_values, **(off if add_options else {})}
            summary = {
                "action": "Add specifications" + (" and new dropdown/filter options" if add_options else ""),
                "product": {"id": product.id, "name": product.name},
                "profile": f"{plan['profile']} (existing)",
                "will_fill": {names[k]: v for k, v in values.items() if k in names} or None,
                "already_set_kept": {names[k]: v for k, v in existing.items() if k in names} or None,
                "fields_filled_after_save": f"{len(existing) + len(values)} of {len(plan['fields'])}",
                "storefront_filters": {
                    "set": filters["set"],
                    "not_an_option_yet": filters["need_new_option"] or None,
                    "no_data_on_source_page": filters["no_data_on_page"] or None,
                },
                "new_options_to_add": {names[k]: v for k, v in off.items()} if add_options else None,
            }
            if not values:
                return {"status": "unchanged", "preview": summary, "note": "Nothing new to fill — every field the source answers is already set."}
            if not inp.get("confirm"):
                note = CONFIRM_NOTE
                if off and not add_options:
                    note += (
                        " Some values from the source page are not existing dropdown options (listed in "
                        "storefront_filters.not_an_option_yet, plus any non-filter dropdowns), so those filters "
                        "would stay empty. Tell the user, and offer to add them as new options — that changes "
                        "the profile for all products; if they want it, preview again with add_missing_options=true."
                    )
                return {"status": "preview", "preview": summary, "note": note}
            profile = db.get(CatalogAttributeProfile, plan["profile_id"])  # type: ignore[union-attr]
            if profile is None:
                _spec_cache.pop(key, None)
                return {"error": "That specification profile no longer exists — preview again."}
            if add_options:
                spec_profile_service.add_options(db, off)  # type: ignore[arg-type]
            written = spec_profile_service.fill_product(db, product, profile, values)  # type: ignore[arg-type]
        else:
            proposal = plan["proposal"]
            category_labels = [c for c in [product.category] if c]
            summary = {
                "action": "Create specification profile (needs approval) and add specifications",
                "product": {"id": product.id, "name": product.name},
                "new_profile": proposal["name"],
                "applies_to_categories": category_labels or ["(set later in Website → Specifications)"],
                "groups": {g["name"]: g["attributes"] for g in proposal["groups"]},
                "fields": sum(len(g["attributes"]) for g in proposal["groups"]),
                "storefront_filters": [
                    {"filter": e["title"], "on": f"{e['group']} > {e['attribute']}", "new_attribute": e["new"], "type": e["kind"], "options": len(e["options"])}
                    for e in (proposal.get("filter_attrs") or [])
                ],
                "note": (
                    "Creates a new specification profile for everyone. The spec rows are fields of their groups; "
                    f"{len(proposal.get('filter_attrs') or [])} of them are the storefront filters of the source shop's category (filterable, with the shop's options) "
                    "- no separate filter group, so nothing is listed twice. Adjust them later in Website → Specifications → Profiles."
                    if proposal.get("filters")
                    else "Creates a new specification profile for everyone; the source shop's category page gave no filters, so all fields are text and not filterable — adjust them later in Website → Specifications → Profiles."
                ),
            }
            if not inp.get("confirm"):
                return {"status": "preview", "preview": summary, "note": CONFIRM_NOTE}
            existing = spec_profile_service.find_profile(db, product=product)  # type: ignore[arg-type]
            if existing is not None:
                _spec_cache.pop(key, None)
                return {"error": f"A '{existing.name}' profile now exists for this product — preview again to fill it instead."}
            try:
                profile = spec_profile_service.create_profile(
                    db,  # type: ignore[arg-type]
                    company_id=product.company_id or company_id or "default",
                    proposal=proposal,
                    category_labels=category_labels,
                )
            except HTTPException as exc:
                db.rollback()  # type: ignore[union-attr]
                return {"error": exc.detail}
            # The profile was built from these same specs, so labels match its fields exactly.
            fields = spec_profile_service.profile_fields(db, profile.id)  # type: ignore[arg-type]
            # spec rows by exact label; each Overview filter gets the option this product falls under
            shown: dict[str, str] = {}
            values, _off, _src = spec_profile_service.map_values_traced(db, company_id, plan["specs"], fields, context=product.name or "", displays=shown)  # type: ignore[arg-type]
            written = spec_profile_service.fill_product(db, product, profile, values, displays=shown)  # type: ignore[arg-type]
            written += spec_profile_service.fill_multi_select(db, product, profile, plan["specs"], extra_text=product.name or "")  # type: ignore[arg-type]
        _spec_cache.pop(key, None)
        db.commit()  # type: ignore[union-attr]
        return {
            "status": "saved",
            "product": {"id": product.id, "name": product.name},
            "profile": profile.name,
            "profile_created": not plan["profile_id"],
            "fields_filled": written,
            "doc_link": f"doc://product/{product.id}",
            "path": f"/website/products?edit={product.id}",
        }

    def fill_product_from_source(inp: dict) -> dict:
        """Product Draft's AI button: fill an EXISTING draft from its own source URL (same pipeline as the import above,
        applied to the row). It starts straight away; only a brand / category that does not exist yet needs approval."""
        if not _can_write_catalog(db, user):
            return {"error": "Filling products needs catalog write permission."}
        res = _resolve_product(str(inp.get("product") or ""))
        if "error" in res:
            return res
        row = res["ok"]
        url = (row.source_url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return {"error": f"'{row.name}' has no source URL - add one in Price Compare's Source column first."}
        confirming = bool(inp.get("confirm"))
        said = inp.get("overrides") if isinstance(inp.get("overrides"), dict) else {}
        said = {k: v for k, v in said.items() if k in _OVERRIDABLE and v not in (None, "")}
        if "profile" in said:
            # the user named a profile in the chat: an existing one (by name), "new" or "none" - anything else is asked back
            choice, names = resolve_profile_choice(db, str(said["profile"]))  # type: ignore[arg-type]
            if choice is None:
                return {
                    "error": f"No single attribute profile matches '{said['profile']}'.",
                    "profiles": names[:60],
                    "note": "Tell the user in one line that no profile has that name, list the closest names from 'profiles' (all of them if there are few), and ask which one to use - or whether to create a new one from the source.",
                }
            said["profile"] = choice
        if said:
            _overrides[url] = {**_overrides.get(url, {}), **said}  # later messages ADD to the earlier ones
        # a follow-up with changes (or 'show the card again') re-uses the page that was already read (no second scrape / AI run)
        extracted = _cache_get(url) if (confirming or said or inp.get("reshow")) else None
        if extracted is None:
            try:
                extracted = extract_from_url(db, url, company_id=company_id)  # type: ignore[arg-type]
            except HTTPException as exc:
                db.rollback()  # type: ignore[union-attr]
                return {"error": exc.detail}
            except Exception as exc:  # noqa: BLE001
                db.rollback()  # type: ignore[union-attr]
                return {"error": f"Could not read the source page: {exc}"}
        if not extracted.draft.name.strip():
            return {"error": "No product found on the source page."}
        extracted = _apply_overrides(extracted, _overrides.get(url, {}))
        d = extracted.draft
        new_things = []
        if d.brand_name and not extracted.matched_brand_id:
            new_things.append(f"brand '{d.brand_name}'")
        if d.category_name and not extracted.matched_category_id:
            new_things.append(f"category '{d.category_name}'")
        has_specs = bool(spec_profile_service.spec_item_count(spec_profile_service.specs_from_draft(d)))
        cat_for_profile = d.category_name or row.category
        picked_profile = _overrides.get(url, {}).get("profile")  # the profile the user named in the chat, if any
        needs_profile = bool(
            has_specs and cat_for_profile
            and (picked_profile == "new" or (picked_profile is None and spec_profile_service.find_profile(db, category_names=[cat_for_profile]) is None))  # type: ignore[arg-type]
        )
        if needs_profile:
            n_attr = spec_profile_service.spec_item_count(spec_profile_service.specs_from_draft(d))
            n_flt = len(d.source_filters or [])
            new_things.append(f"specification profile '{cat_for_profile}' ({n_attr} attributes from the source" + (f", {n_flt} filters from the source shop" if n_flt else "") + ")")
        if not confirming:
            # Always review first: what the AI collected from the source and what it will be connected to.
            _cache_set(url, extracted)
            review = fill_review(db, company_id, row, extracted)  # type: ignore[arg-type]
            return {
                "status": "preview",
                # the drawer shows this as a review card (gallery, price / old price, category / brand / specification
                # profile pickers the admin can change) with Accept / Deny - nothing more to show in words
                "review": review,
                "needs_approval": (f"This will create: {', '.join(new_things)}. " if new_things else "")
                + "The admin can pick existing ones in the card.",
                "product": {"id": row.id, "name": row.name},
                "note": (
                    "Nothing was saved. A review card with all the collected data is now shown to the user, who "
                    "approves it there. Reply with a SHORT message asking them to check it and press Accept - do NOT "
                    "repeat the details. " + _profile_line(review["profile"]) +
                    " Call again with confirm=true only if the user explicitly agrees in words."
                ),
            }
        _extract_cache.pop(url, None)
        chosen_profile = _overrides.pop(url, {}).get("profile")  # the profile the user named in the chat goes with the fill
        try:
            row = apply_fill(db, user, company_id, row, extracted, profile_id=chosen_profile)  # type: ignore[arg-type]
        except HTTPException as exc:
            db.rollback()  # type: ignore[union-attr]
            return {"error": exc.detail}
        except Exception as exc:  # noqa: BLE001
            db.rollback()  # type: ignore[union-attr]
            return {"error": f"Could not fill the product: {exc}"}
        return {
            "status": "filled",
            "product": {"id": row.id, "name": row.name},
            "doc_link": f"doc://product/{row.id}",
            "path": f"/website/products?edit={row.id}",
            "price": str(row.price), "compare_at_price": str(row.compare_at_price) if row.compare_at_price else None,
            "brand": row.brand, "category": row.category, "images": len(d.images or []),
            "images_kept": getattr(row, "_images_reused", 0), "image_warnings": getattr(row, "_image_warnings", []),
            "specifications": _spec_result(row, extracted),
            "note": "Tell the user briefly what was filled (price/offer, brand, category, images, specs, description, SEO) and that the product stays a draft. To link the product use EXACTLY the doc_link value as the markdown link target (never invent a /catalog path).",
        }

    def list_spec_profiles(inp: dict) -> dict:
        if db is None:
            return {"error": "No database session."}
        query = str(inp.get("query") or "").strip()
        want = set(_profile_tokens(query))
        out = []
        for p in _all_profiles(db):  # type: ignore[arg-type]
            if want and not (want <= set(_profile_tokens(p.name))):
                continue
            try:
                labels = json.loads(p.category_labels or "[]")
            except (TypeError, ValueError):
                labels = []
            out.append({
                "id": p.id,
                "name": p.name,
                "attributes": len(spec_profile_service.profile_fields(db, p.id)),  # type: ignore[arg-type]
                "categories": [str(x) for x in labels][:4] if isinstance(labels, list) else [],
            })
        return {
            "count": len(out),
            "profiles": out,
            "note": "Show the profile NAMES in one short line (not ids). The user picks one in the review card's 'Specification profile' dropdown or tells you the name; if they name one, call fill_product_from_source with overrides.profile. If the list is empty, say there is no profile yet and a new one can be created from the source.",
        }

    return [
        OrchestratorTool(
            definition=AIToolDefinition(
                name="import_product_from_url",
                description=(
                    "Import a product into the catalog from its page on another website (e.g. a link from "
                    "startech.com.bd, ryans.com, any store product page). Reads the page, extracts name, price, "
                    "brand, category, images, specs and warranty, and creates it as a draft product — auto-creating "
                    "the brand and/or category if they do not already exist. CALL THIS FIRST (without confirm) the "
                    "moment the user gives a product URL to import — it returns a preview; nothing is created until "
                    "confirm=true. If the preview's 'warnings' list says this URL was already imported, tell the user "
                    "plainly and ask whether they still want a duplicate before calling confirm=true — do not silently "
                    "proceed. Use for 'import this product', 'upload this from the link', 'add this to our "
                    "catalog'. A CATEGORY / listing link (many products) is not a product page - when the user gives a "
                    "category link together with a product link and asks for an attribute / specification profile, use "
                    "create_spec_profile_from_links instead."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Full product page URL"},
                        "profile": {
                            "type": "string",
                            "description": "The ATTRIBUTE / SPECIFICATION PROFILE the user wants for this product, by the name they said ('Laptop' ...). Use it when they say e.g. 'laptop attribute profile use koro' after a preview (call again with the same url + profile, still without confirm). 'new' = create a new profile from the page, 'none' = no profile.",
                        },
                        "confirm": {
                            "type": "boolean",
                            "description": "false/omitted = preview only (nothing written). true = create — ONLY after the user has explicitly confirmed the preview in this conversation.",
                        },
                    },
                    "required": ["url"],
                },
            ),
            handler=import_product_from_url,
            risk_tier=RiskTier.WRITE,
            module="catalog",
        ),
        OrchestratorTool(
            definition=AIToolDefinition(
                name="add_product_seo",
                description=(
                    "Set a product's on-page SEO fields — Focus Keyphrase, Meta title, Meta description. Call this "
                    "only after asking the user whether they want SEO generated and they said yes (e.g. right after "
                    "import_product_from_url creates a product). Omit any of focus_keyphrase/meta_title/"
                    "meta_description (always, unless the user typed the exact value they want) — the tool writes them from the "
                    "product's specs following the company's SEO rule; values you make up yourself are ignored. "
                    "CALL THIS FIRST without confirm to preview the values, then confirm=true "
                    "once the user agrees."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "product": {"type": "string", "description": "Product name, SKU or id"},
                        "focus_keyphrase": {"type": "string", "description": "Optional — auto-generated from brand/category if omitted"},
                        "meta_title": {"type": "string", "description": "Optional — auto-generated from the product name if omitted"},
                        "meta_description": {"type": "string", "description": "Optional — auto-generated from the short description if omitted"},
                        "confirm": {
                            "type": "boolean",
                            "description": "false/omitted = preview only (nothing written). true = save — ONLY after the user has explicitly confirmed.",
                        },
                    },
                    "required": ["product"],
                },
            ),
            handler=add_product_seo,
            risk_tier=RiskTier.WRITE,
            module="catalog",
        ),
        OrchestratorTool(
            definition=AIToolDefinition(
                name="add_product_specs",
                description=(
                    "Add a product's specifications from its source data (the spec table imported from its source "
                    "page) into the structured specification profile. If the product's category already has a "
                    "profile, the preview shows the values that will be filled. If no profile exists, the preview "
                    "proposes creating one from the source spec groups — creating a profile needs the user's "
                    "explicit approval. Use after import_product_from_url says no profile exists and the user agreed, "
                    "or when the user asks to add/fill specifications for a product. CALL FIRST without confirm, show "
                    "the preview, then call again with the same arguments and confirm=true only after the user agrees."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "product": {"type": "string", "description": "Product name, SKU or id"},
                        "profile_name": {
                            "type": "string",
                            "description": "Only when creating a new profile and the user named it — defaults to the product's category",
                        },
                        "add_missing_options": {
                            "type": "boolean",
                            "description": "true only after the user agreed to add the source values that are not existing dropdown/filter options as new options (changes the profile for all products)",
                        },
                        "confirm": {
                            "type": "boolean",
                            "description": "false/omitted = preview only (nothing written). true = save — ONLY after the user has explicitly confirmed.",
                        },
                    },
                    "required": ["product"],
                },
            ),
            handler=add_product_specs,
            risk_tier=RiskTier.WRITE,
            module="catalog",
        ),
        OrchestratorTool(
            definition=AIToolDefinition(
                name="create_spec_profile_from_links",
                description=(
                    "Create a SPECIFICATION (attribute) PROFILE - and only the profile, no product - from two links: a CATEGORY page of "
                    "a source shop (e.g. https://www.startech.com.bd/neckband - its sidebar filters become filters ON the profile's "
                    "spec attributes, no separate filter group) and ONE PRODUCT page of that category (its spec table becomes the spec groups and fields). Use when "
                    "the user gives a category link plus a product link and asks for an attribute / specification profile ('category theke "
                    "filter and product theke attribute niye profile baniye felo', optionally with a name such as 'Neckband Specification'). "
                    "NEVER use import_product_from_url for these - a category link is not a product. Take the user's profile name exactly "
                    "as given. CALL FIRST without confirm, show the preview (groups, field count, every storefront filter with its type and "
                    "option count), then call again with the same arguments and confirm=true only after the user agrees."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "category_url": {"type": "string", "description": "The category / listing page link (has the filter sidebar)"},
                        "product_url": {"type": "string", "description": "One product page link of that category (has the specification table)"},
                        "profile_name": {"type": "string", "description": "The profile's name as the user wrote it (e.g. 'Neckband Specification'); defaults to the product's category"},
                        "confirm": {
                            "type": "boolean",
                            "description": "false/omitted = preview only (nothing written). true = create - ONLY after the user has explicitly confirmed the preview.",
                        },
                    },
                    "required": ["category_url", "product_url"],
                },
            ),
            handler=create_spec_profile_from_links,
            risk_tier=RiskTier.WRITE,
            module="catalog",
        ),
        OrchestratorTool(
            definition=AIToolDefinition(
                name="fill_product_from_source",
                description=(
                    "Fill an EXISTING draft product from its own source URL (the Source link saved on the product): "
                    "description, price / offer (compare-at), stock, brand, category, warranty, specifications and filters, "
                    "images (originals, 500x500 WebP) and SEO, following docs/AI/product-upload.md. Use when asked to "
                    "'fill / upload / complete this product from its source'. ALWAYS call WITHOUT confirm first: it reads "
                    "the source and returns status=preview with `preview_markdown` (new title, category, brand, "
                    "specification profile it will connect to, price, images, SEO ...) and saves NOTHING - show that "
                    "text exactly as written and ask the user to approve. Only after they explicitly approve, call again "
                    "with confirm=true: that updates the title and fills the product."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "product": {"type": "string", "description": "Product id (preferred), SKU or name"},
                        "overrides": {
                            "type": "object",
                            "description": "ONLY when a review card from an EARLIER fill_product_from_source call in THIS conversation is open: the values the user just dictated (e.g. {\"price\": 130000}). They are MERGED into the review and the card is shown again. If no review is open, a direct change (price, compare_at_price, name, tags ... 'dao' / 'koro') is update_product, never this.",
                            "properties": {
                                "price": {"type": "number"},
                                "compare_at_price": {"type": "number"},
                                "name": {"type": "string"},
                                "model": {"type": "string"},
                                "warranty": {"type": "string"},
                                "origin": {"type": "string"},
                                "stock_status": {"type": "string", "enum": ["in_stock", "out_of_stock", "pre_order", "coming_soon"]},
                                "profile": {
                                    "type": "string",
                                    "description": "The ATTRIBUTE / SPECIFICATION PROFILE the user wants for this product, by the name they said ('Laptop', 'Monitor' ...). Use it when they say e.g. 'laptop attribute profile use koro'. 'new' = create a new profile from the source page, 'none' = no profile (specs stay on the product only).",
                                },
                            },
                        },
                        "reshow": {"type": "boolean", "description": "true = show the open review card again without changing anything (e.g. the user asked for the profile list / dropdown)"},
                        "confirm": {"type": "boolean", "description": "true only after the user approved the preview"},
                    },
                    "required": ["product"],
                },
            ),
            handler=fill_product_from_source,
            risk_tier=RiskTier.WRITE,
            module="catalog",
        ),
        OrchestratorTool(
            definition=AIToolDefinition(
                name="list_spec_profiles",
                description=(
                    "List the existing attribute / specification profiles (name, how many attributes, its categories). Use when the user asks "
                    "'attribute profile list dao', which profiles exist, or wants to choose one: show the names in one short line and tell them "
                    "they can pick it in the review card's 'Specification profile' dropdown or say the name. Read-only."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "Optional: only profiles whose name contains these words"}},
                },
            ),
            handler=list_spec_profiles,
            risk_tier=RiskTier.READ,
            module="catalog",
        ),
    ]
