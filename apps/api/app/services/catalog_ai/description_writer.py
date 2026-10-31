"""Product description writer — rule A10 of docs/AI/product-upload.md.

The import never copies the source text: the page's facts are given to the model, which writes an original, SEO-friendly
description (the company's `catalog.product.description` preset when it has one, DEFAULT_DESCRIPTION_RULE otherwise), and
the result is CHECKED here against the hard requirements - at least 300 words, the focus keyphrase in the first paragraph and
in a heading, at least 2 <h2> and 3 <h3> headings, a Frequently Asked Questions section, and at least 2 internal links to
pages of OUR storefront that really exist (category, brand within the category, related products) - and rewritten (up to
MAX_ATTEMPTS times, with the failed checks named) until it passes. Missing links are added at the end as a last resort. The
best attempt is kept when none passes. Never raises: with no model / on an error the caller keeps the extracted text.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Optional
from urllib.parse import quote, unquote

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.catalog_brand import CatalogBrand
from app.models.catalog_category import CatalogCategory
from app.models.catalog_product import CatalogProduct
from app.schemas.catalog_ai_import import ProductDraft
from app.services.ai import preset_service
from app.services.catalog_ai import seo_writer
from app.services.catalog_ai.llm_extractor import generate_structured
from app.services.provider_mapping_service import slugify

MIN_WORDS = 300
MIN_H2 = 2
MIN_H3 = 3
MIN_LINKS = 2
MAX_ATTEMPTS = 3
FAQ_TITLE = "Frequently Asked Questions"

# The description rule used when the company has no \`catalog.product.description\` preset: what a search engine and a shopper both want.
DEFAULT_DESCRIPTION_RULE = (
    "Write an original, helpful, SEO-friendly product page text in clear, natural English (short paragraphs, 2-3 sentences each). "
    "Structure: (1) an intro <p> that names the product and contains the focus keyphrase; (2) <h2> sections such as the product "
    "overview, key features (a <ul> of 4-6 items with the main specs in <strong>), performance / design / battery / connectivity "
    "(whatever the product type has), who it is for, warranty and buying information - each <h2> with <h3> sub-headings where it "
    "helps; (3) put the focus keyphrase in at least one <h2> or <h3> heading and use it only 3-4 times in total - never stuff it; "
    "(4) finish with an <h2> '" + FAQ_TITLE + "' holding 3-4 <h3> questions (each ending with '?') answered in one or two sentences "
    "from the facts given (warranty, compatibility, key specs, what is in the box if known); (5) weave the internal links into "
    "sentences of the body with descriptive anchor text, never 'click here'. Use only the facts given - no invented specs, prices, "
    "offers or delivery promises, no other store's name, no 'best in the world' claims."
)

_SCHEMA = {
    "type": "object",
    "properties": {"description": {"type": "string", "description": "The description as HTML (p, h2, h3, ul, li, strong, a only)"}},
    "required": ["description"],
}
_TAG = re.compile(r"<[^>]+>")
_HREF = re.compile(r"<a\b[^>]*\bhref\s*=\s*[\"']([^\"']+)[\"']", re.I)


def keyphrase_for(draft: ProductDraft) -> str:
    """The focus keyphrase of a product that is not saved yet - the SAME rule the SEO fields use afterwards (brand + model, or the
    leading words of the name, whichever is inside the URL slug), so the description and the SEO panel agree on one keyphrase."""
    pseudo = SimpleNamespace(name=draft.name, brand=draft.brand_name, model=draft.model, slug=slugify(draft.name) or "", category=draft.category_name)
    base = " ".join(w for w in [draft.brand_name, draft.model] if w).strip() or draft.name
    return seo_writer._keyphrase_for_slug(pseudo, base)  # type: ignore[arg-type]


def plain(html_text: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", html_text or "")).strip()


def _brand_link(db: Session, company_id: Optional[str], draft: ProductDraft, cat_slug: str) -> Optional[dict]:
    """The brand's own page ("/toshiba"): the slug of the brand we have, or - when Aladin is about to create it - the slug that creation
    will give it (same rule). Only when that slug is also a category's does the link fall back to "/<category>?brand=<Brand>"."""
    name = (draft.brand_name or "").strip()
    if not name:
        return None
    from app.services.catalog_ai.importer_service import _find_brand, _unique_brand_slug

    row = _find_brand(db, company_id or "default", name)
    slug = row.slug if row is not None else _unique_brand_slug(db, slugify(name) or "brand")
    clash = db.query(CatalogCategory.id).filter(CatalogCategory.slug == slug).first() is not None
    href = f"/{cat_slug}?brand={quote(name)}" if clash else f"/{slug}"
    out = {"href": href, "label": name, "kind": "brand"}
    if row is None:
        out["pending"] = True
    return out


def internal_links(db: Session, company_id: Optional[str], draft: ProductDraft) -> list[dict]:
    """Pages of OUR storefront the description may link to (they exist, so no link is ever a 404): the product's category and its
    parent ("/<category-slug>"), the brand inside that category ("/<category-slug>?brand=<Brand>") and up to 2 related published
    products ("/<product-slug>"). [] when the category is not one of ours yet."""
    cid = company_id or "default"
    out: list[dict] = []
    leaf = (draft.category_name or "").split(">")[-1].strip()
    if not leaf:
        return out
    try:
        cat = (
            db.query(CatalogCategory)
            .filter(CatalogCategory.company_id == cid, CatalogCategory.is_active.is_(True), CatalogCategory.channel == "catalog", CatalogCategory.name.ilike(leaf))
            .first()
        )
        if cat is None:
            # Aladin creates the category when the product is created: link to the slug that creation will give it (same rule), so
            # the link works the moment the page is live. repair_links() re-checks it against the real slug afterwards.
            from app.services.catalog_ai.importer_service import _unique_category_slug

            slug = _unique_category_slug(db, slugify(leaf) or "category")
            out.append({"href": f"/{slug}", "label": leaf, "kind": "category", "pending": True})
            link = _brand_link(db, company_id, draft, slug)
            if link:
                out.append(link)
            return out
        out.append({"href": f"/{cat.slug}", "label": cat.name, "kind": "category"})
        parent = db.get(CatalogCategory, cat.parent_id) if cat.parent_id else None
        if parent is not None and parent.is_active and parent.slug != cat.slug:
            out.append({"href": f"/{parent.slug}", "label": parent.name, "kind": "category"})
        link = _brand_link(db, company_id, draft, cat.slug)
        if link:
            out.append(link)
        related = (
            db.query(CatalogProduct)
            .filter(CatalogProduct.company_id == cid, CatalogProduct.status == "published", CatalogProduct.category.ilike(cat.name), CatalogProduct.name != draft.name)
            .order_by(CatalogProduct.updated_at.desc())
            .limit(12)
            .all()
        )
        brand_key = (draft.brand_name or "").strip().lower()
        related.sort(key=lambda p: 0 if brand_key and (p.brand or "").strip().lower() == brand_key else 1)  # same brand first
        for p in related[:2]:
            out.append({"href": f"/{p.slug}", "label": p.name, "kind": "product"})
    except Exception:  # noqa: BLE001 - links are an upgrade, never a reason to fail
        db.rollback()
        return []
    return out


def failures(html_text: str, keyphrase: str, links: Optional[list[dict]] = None) -> list[str]:
    """Which hard requirements the description misses (empty list = passes)."""
    out: list[str] = []
    words = len(plain(html_text).split())
    if words < MIN_WORDS:
        out.append(f"it has {words} words — at least {MIN_WORDS} are required")
    h2 = len(re.findall(r"<h2\b", html_text, re.I))
    h3 = len(re.findall(r"<h3\b", html_text, re.I))
    if h2 < MIN_H2:
        out.append(f"it has {h2} <h2> headings — at least {MIN_H2} are required")
    if h3 < MIN_H3:
        out.append(f"it has {h3} <h3> headings — at least {MIN_H3} are required")
    if re.search(r"<h1\b", html_text, re.I):
        out.append("it contains an <h1> — the product title is the page's only <h1>")
    first = re.search(r"<p\b[^>]*>(.*?)</p>", html_text, re.I | re.S)
    if not first or keyphrase.lower() not in plain(first.group(1)).lower():
        out.append(f"the first paragraph must contain the focus keyphrase '{keyphrase}' exactly")
    heads = re.findall(r"<h[23]\b[^>]*>(.*?)</h[23]>", html_text, re.I | re.S)
    if not any(keyphrase.lower() in plain(h).lower() for h in heads):
        out.append(f"at least one <h2> or <h3> heading must contain the focus keyphrase '{keyphrase}'")
    faq = re.search(r"<h2\b[^>]*>[^<]*frequently asked[^<]*</h2>(.*)", html_text, re.I | re.S)
    questions = [q for q in re.findall(r"<h3\b[^>]*>(.*?)</h3>", faq.group(1), re.I | re.S) if plain(q).endswith("?")] if faq else []
    if len(questions) < 2:
        out.append(f"it needs an <h2> '{FAQ_TITLE}' followed by at least 2 <h3> questions ending with '?'")
    if links:
        allowed = {l["href"] for l in links}
        used = [h for h in _HREF.findall(html_text)]
        good = {h for h in used if h in allowed}
        need = min(MIN_LINKS, len(allowed))
        first_cat = next((l for l in links if l["kind"] == "category"), None)
        brand = next((l for l in links if l["kind"] == "brand"), None)
        for must_have in (first_cat, brand):
            if must_have is not None and must_have["href"] not in good:
                out.append(f"it must link to {must_have['href']} (the {must_have['kind']} page, anchor text '{must_have['label']}')")
        if len(good) < need:
            out.append(f"it links to {len(good)} of our pages — at least {need} different ones from the allowed list are required")
        stray = [h for h in used if h not in allowed]
        if stray:
            out.append("it links to " + ", ".join(sorted(set(stray))[:3]) + " — link ONLY to the allowed URLs")
    return out


_ANCHOR = re.compile(r"<a\b[^>]*?\bhref\s*=\s*([\"'])([^\"']+)\1[^>]*>(.*?)</a>", re.I | re.S)


def repair_links(db: Session, company_id: Optional[str], product) -> str:
    """After the product (and its category) exist: every internal link of its description must point at a page that exists. A link to a
    category slug that was predicted but came out different (or was never created) is pointed at the product's real category; one that
    still matches nothing is unlinked (its text stays); a link repeated twice is linked once. Returns the description (unchanged when fine)."""
    html = product.description or ""
    if "<a" not in html.lower():
        return html
    cid = company_id or "default"
    real = db.get(CatalogCategory, product.category_id) if getattr(product, "category_id", None) else None
    real_slug = real.slug if real is not None and real.is_active else None
    real_brand = db.get(CatalogBrand, product.brand_id) if getattr(product, "brand_id", None) else None
    brand_base = slugify(real_brand.name) if real_brand is not None else ""
    # the product's own category and its parents: the only categories its description may point at
    chain: dict[str, str] = {}
    node, hops = real, 0
    while node is not None and hops < 8:
        chain[node.slug] = node.name
        node = db.get(CatalogCategory, node.parent_id) if node.parent_id else None
        hops += 1

    def exists(slug: str) -> bool:
        if not slug:
            return False
        if db.query(CatalogCategory.id).filter(CatalogCategory.slug == slug, CatalogCategory.is_active.is_(True)).first():
            return True
        if db.query(CatalogBrand.id).filter(CatalogBrand.slug == slug).first():
            return True
        return bool(db.query(CatalogProduct.id).filter(CatalogProduct.slug == slug, CatalogProduct.company_id == cid).first())

    seen: set[str] = set()

    def fix(m: "re.Match[str]") -> str:
        href, text = m.group(2), m.group(3)
        if not href.startswith("/"):
            return m.group(0)  # not an internal link: leave it alone
        base, _, query = href.partition("?")
        slug = base.strip("/")
        other = db.query(CatalogCategory).filter(CatalogCategory.slug == slug, CatalogCategory.is_active.is_(True)).first() if slug else None
        if other is not None and chain and slug not in chain:
            # a real category, but not this product's (the text was written about a guessed one): point at the product's own category
            text = re.sub(re.escape(other.name), real.name, text, flags=re.I)
            href = f"/{real_slug}" + (f"?{query}" if query else "")
            base, slug = f"/{real_slug}", real_slug
        if not exists(slug):
            if real_brand is not None and not query and brand_base and (slug == brand_base or slug.startswith(brand_base + "-")):
                href = f"/{real_brand.slug}"  # the brand's slug came out different from the predicted one
            elif real_slug and (query.startswith("brand=") or "/" not in slug):
                href = f"/{real_slug}" + (f"?{query}" if query else "")
            else:
                return text  # nothing to point at: keep the words, drop the link
        if href.partition("?")[2].startswith("brand="):
            # the older "/<category>?brand=<Name>" form: a brand that has its own page links to it ("/toshiba")
            brand = db.query(CatalogBrand).filter(CatalogBrand.name.ilike(unquote(href.partition("?")[2][6:]))).first()
            if brand is not None and not db.query(CatalogCategory.id).filter(CatalogCategory.slug == brand.slug).first():
                href = f"/{brand.slug}"
        if href in seen:
            return text
        seen.add(href)
        return f'<a href="{href}">{text}</a>'

    return _ANCHOR.sub(fix, html)


def _add_missing_links(html_text: str, links: list[dict]) -> str:
    """Last resort when the model keeps forgetting: a closing paragraph with the links the text still lacks."""
    used = set(_HREF.findall(html_text))
    need = min(MIN_LINKS, len(links)) - len({h for h in used if h in {l["href"] for l in links}})
    if need <= 0:
        return html_text
    extra = [l for l in links if l["href"] not in used][: max(need, 2)]
    if not extra:
        return html_text
    anchors = ", ".join(f'<a href="{l["href"]}">{l["label"]}</a>' for l in extra)
    return html_text.rstrip() + f"<p>Explore more: {anchors}.</p>"


def _facts(draft: ProductDraft, source_text: str) -> str:
    specs = "\n".join(f"- {i.label}: {i.value}" for g in draft.specifications for i in g.items)
    lines = [
        ("Product name", draft.name), ("Brand", draft.brand_name), ("Model", draft.model),
        ("Category", draft.category_name), ("Warranty", draft.warranty), ("Origin", draft.origin),
    ]
    head = "\n".join(f"{k}: {v}" for k, v in lines if v)
    return (
        f"{head}\n\nSpecifications:\n{specs or '(none)'}\n\nKey points from the page:\n{draft.short_description or '(none)'}"
        f"\n\nSource description (facts only — do not copy its sentences):\n{source_text[:2500] or '(none)'}"
    )


def write_description(
    db: Session, company_id: Optional[str], draft: ProductDraft, *, source_text: str
) -> Optional[str]:
    rules = preset_service.active_rules(db, company_id, ["general", "catalog", "catalog.product.description"])
    keyphrase = keyphrase_for(draft)
    links = internal_links(db, company_id, draft)
    if "catalog.product.description" in rules:
        rule_block = preset_service.field_rules_block(rules, {"catalog.product.description": "description"})
    else:
        rule_block = "Description rules:\n" + DEFAULT_DESCRIPTION_RULE
    link_block = (
        "\n- internal links: use the category link and the brand link (kind: category / brand) and, besides them, "
        "any others - at least " + str(min(MIN_LINKS, len(links))) + " DIFFERENT ones in all, from the URLs below, each as <a href=\"URL\">anchor text</a> inside a body "
        "sentence (not in the first paragraph); the link text must name the page it opens (its label below, e.g. 'Toshiba Hard Disk Drive' - never this "
        "product's own name, never 'click here'); use the URL exactly as written and no other link:\n"
        + "\n".join(f"    {l['href']}  — {l['kind']}: {l['label']}" for l in links)
        if links
        else "\n- no links (none of our pages exist for this product yet)."
    )
    base = (
        "Write the product description for this product of ours.\n\n"
        f"{_facts(draft, source_text)}\n\n"
        + rule_block
        + "\n\nHard requirements (checked automatically; the text is rejected and rewritten if any fails):\n"
        f"- at least {MIN_WORDS} words of visible text, aiming for {MIN_WORDS + 50}-{MIN_WORDS + 250} - do not pad or repeat yourself;\n"
        f"- the first paragraph (<p>) contains the focus keyphrase \"{keyphrase}\" exactly as written (capitalise it naturally);\n"
        f"- at least one <h2> or <h3> heading contains the focus keyphrase;\n"
        f"- at least {MIN_H2} <h2> and {MIN_H3} <h3> headings; no <h1>;\n"
        f"- an <h2> \"{FAQ_TITLE}\" with at least 2 <h3> questions ending with '?', answered from the facts above;"
        + link_block
        + "\n- HTML only: <p>, <h2>, <h3>, <ul>, <li>, <strong>, <a>; the first element is the intro <p>;\n"
        "- original wording, only facts given above, no other store's name, no prices."
    )
    best: Optional[tuple[int, str]] = None
    problems: list[str] = []
    for attempt in range(MAX_ATTEMPTS):
        prompt = base if not problems else base + "\n\nYour previous attempt was rejected because: " + "; ".join(problems) + ". Fix all of it."
        try:
            data = generate_structured(prompt, _SCHEMA, db=db, company_id=company_id,
                                       system="You write unique, SEO-friendly product descriptions as clean HTML.")
        except HTTPException:
            break
        text = str(data.get("description") or "").strip()
        if not text:
            continue
        problems = failures(text, keyphrase, links)
        if best is None or len(problems) < best[0]:
            best = (len(problems), text)
        if not problems:
            break
    if best is None:
        return None
    return _add_missing_links(best[1], links) if links else best[1]


# ------------------------------------------------------------------------------------------ short description (A9)
SHORT_POINTS = 4
SHORT_MAX_CHARS = 80
_NOT_A_FEATURE = re.compile(r"^\s*(mpn|model(\s+(name|number|no\.?))?|sku|part\s*(number|no\.?)|upc|ean|barcode|product\s*code)\b", re.I)
_LABEL_VALUE = re.compile(r"^[A-Za-z][A-Za-z0-9 ./&()'-]{1,28}:\s+\S")
_SHORT_SCHEMA = {
    "type": "object",
    "properties": {"bullets": {"type": "array", "items": {"type": "string"}, "description": "Exactly 4 key features, each written as 'Label: value' (e.g. 'RAM: 16GB DDR5')"}},
    "required": ["bullets"],
}


# ---- specification values (ai.md / product-upload.md A11): re-worded, the main value verified unchanged ----
SPEC_REWRITE_MIN_CHARS = 40   # shorter values (numbers, units, yes / no, one option) are never touched
SPEC_REWRITE_MAX_ITEMS = 40
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_WORD_WITH_DIGIT = re.compile(r"[A-Za-z]*\d[A-Za-z0-9.+/-]*")
_SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "values": {
            "type": "array",
            "items": {"type": "object", "properties": {"i": {"type": "integer"}, "value": {"type": "string"}}, "required": ["i", "value"]},
        }
    },
    "required": ["values"],
}


def _numbers(text: str) -> list[str]:
    return sorted(n.replace(",", "") for n in _NUM.findall(text or ""))


def _tokens(text: str) -> set[str]:
    return {t.lower().strip(".,;:") for t in _WORD_WITH_DIGIT.findall(text or "")}


def spec_value_ok(old: str, new: str) -> bool:
    """The re-worded value keeps the main value: the same numbers, the same figure-bearing names (USB 3.2, HDMI 2.1, i7-13700H ...),
    about the same length. Anything else -> the original stays."""
    new = (new or "").strip()
    if not new or "<" in new or len(new) > max(60, int(len(old) * 1.4)) or len(new) < int(len(old) * 0.4):
        return False
    return _numbers(old) == _numbers(new) and _tokens(old) <= _tokens(new)


def rewrite_spec_values(db: Session, company_id: Optional[str], draft: ProductDraft) -> ProductDraft:
    """Long descriptive specification values re-worded by the model (consistent wording / formatting, not a word-for-word copy of the
    source shop) - the main value must stay exactly right, so each rewrite is checked (`spec_value_ok`) and a failing one keeps the
    original. Needs the `catalog.product.spec_values` preset; the draft is returned unchanged without it or on any failure."""
    rules = preset_service.active_rules(db, company_id, ["general", "catalog", "catalog.product.spec_values"])
    if "catalog.product.spec_values" not in rules:
        return draft
    todo: list[tuple[int, int, str, str]] = []  # (group index, item index, label, value)
    for gi, g in enumerate(draft.specifications):
        for ii, it in enumerate(g.items):
            if len(it.value or "") >= SPEC_REWRITE_MIN_CHARS and ";" not in it.value and "warrant" not in it.label.lower():  # "A; B; C" = option lists (filters)
                todo.append((gi, ii, it.label, it.value))
    todo = todo[:SPEC_REWRITE_MAX_ITEMS]
    if not todo:
        return draft
    prompt = (
        "Rewrite these specification values of a product, following the company rule below. Return every value with its number `i`.\n\n"
        + preset_service.field_rules_block(rules, {"catalog.product.spec_values": "specification values"})
        + "\n\nHard requirements (checked automatically; a value that fails is dropped and the original kept):\n"
        "- keep every number, unit, version, port / standard / model name and brand exactly as given - nothing added, nothing dropped;\n"
        "- plain text, no HTML, about the same length, no seller name.\n\nValues:\n"
        + "\n".join(f"{n}. [{label}] {value}" for n, (_g, _i, label, value) in enumerate(todo))
    )
    try:
        data = generate_structured(prompt, _SPEC_SCHEMA, db=db, company_id=company_id, system="You reword product specification values without changing any fact.")
    except HTTPException:
        return draft
    groups = [g.model_copy(update={"items": list(g.items)}) for g in draft.specifications]
    for row in data.get("values") or []:
        try:
            n = int(row["i"])
            gi, ii, _label, old = todo[n]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        new = re.sub(r"\s+", " ", str(row.get("value") or "")).strip()
        if new and new != old and spec_value_ok(old, new):
            groups[gi].items[ii] = groups[gi].items[ii].model_copy(update={"value": new})
    return draft.model_copy(update={"specifications": groups})


def short_failures(lines: list[str]) -> list[str]:
    out: list[str] = []
    if len(lines) != SHORT_POINTS:
        out.append(f"it has {len(lines)} points - exactly {SHORT_POINTS} are required")
    for ln in lines:
        if _NOT_A_FEATURE.match(ln):
            out.append(f"'{ln}' is a model / part number - never a bullet")
        elif not _LABEL_VALUE.match(ln):
            out.append(f"'{ln}' is not in 'Label: value' form - write it like 'RAM: 16GB DDR5'")
        elif len(ln) > SHORT_MAX_CHARS:
            out.append(f"'{ln[:30]}...' is longer than {SHORT_MAX_CHARS} characters")
    return out


def write_short_description(
    db: Session, company_id: Optional[str], draft: ProductDraft, *, source_points: list[str]
) -> Optional[list[str]]:
    """Rule A9: exactly 4 bullet points, the key features, each as 'Label: value' ('RAM: 16GB') like the storefront's key-feature
    list - never a model / MPN / part number. Checked and rewritten like the
    description. Needs the `catalog.product.short_description` preset; None on any failure (the caller keeps its text)."""
    rules = preset_service.active_rules(db, company_id, ["general", "catalog", "catalog.product.short_description"])
    if "catalog.product.short_description" not in rules:
        return None
    base = (
        "Write the short description (key features) of this product of ours.\n\n"
        f"{_facts(draft, '')}\n\nThe source page's own highlight lines (facts only - do NOT copy them):\n"
        + ("\n".join(f"- {p}" for p in source_points) or "(none)")
        + "\n\n"
        + preset_service.field_rules_block(rules, {"catalog.product.short_description": "short description"})
        + "\n\nHard requirements (checked automatically; rejected and rewritten if any fails):\n"
        f"- exactly {SHORT_POINTS} bullet points;\n"
        "- each one a key feature a shopper decides on (processor, memory / storage, display, standout feature, "
        "connectivity, battery ...), written as 'Label: value' with a short label, e.g. 'Processor: Intel Core Ultra 5', "
        "'RAM: 16GB DDR5', 'Display: 14\" WUXGA touch, 400 nits', 'Battery: up to 60 days';\n"
        "- every line has the form 'Label: value' (one colon); NEVER a model number, MPN, SKU or part number;\n"
        f"- under {SHORT_MAX_CHARS} characters each; no seller name, no price; only facts given above."
    )
    best: Optional[tuple[int, list[str]]] = None
    problems: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        prompt = base if not problems else base + "\n\nYour previous attempt was rejected because: " + "; ".join(problems) + ". Fix all of it."
        try:
            data = generate_structured(prompt, _SHORT_SCHEMA, db=db, company_id=company_id,
                                       system="You write concise, benefit-led product key-feature bullets.")
        except HTTPException:
            break
        # drop a bullet marker or list number ("- ", "• ", "1. ") - never the figures that start a feature ("16GB", '14" ...')
        lines = [re.sub(r"^\s*(?:[-•*·]+\s*|\d+[.)]\s+)", "", str(b)).strip() for b in (data.get("bullets") or [])]
        lines = [ln for ln in lines if ln]
        problems = short_failures(lines)
        if best is None or len(problems) < best[0]:
            best = (len(problems), lines)
        if not problems:
            break
    return best[1] if best and best[1] else None
