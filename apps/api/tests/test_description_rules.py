"""Aladin's product description checks: structure, keyphrase placement, FAQ and links to pages of OUR storefront."""
from app.services.catalog_ai import description_writer as dw

KP = "acer nitro 5"
LINKS = [
    {"href": "/gaming-laptop", "label": "Gaming Laptop", "kind": "category"},
    {"href": "/gaming-laptop?brand=Acer", "label": "Acer Gaming Laptop", "kind": "brand"},
]
FILL = " ".join(["word"] * 40)


def good(**over):
    parts = {
        "intro": f"<p>The Acer Nitro 5 is built for play. {FILL}</p>",
        "h2a": f"<h2>Why the Acer Nitro 5 stands out</h2><p>See our <a href=\"/gaming-laptop\">gaming laptops</a>. {FILL}</p>",
        "h2b": f"<h2>Key features</h2><h3>Display</h3><p>{FILL}</p><h3>Cooling</h3><p>{FILL}</p><h3>Ports</h3><p>More <a href=\"/gaming-laptop?brand=Acer\">Acer gaming laptops</a>. {FILL}</p>",
        "faq": f"<h2>{dw.FAQ_TITLE}</h2><h3>Does it have a warranty?</h3><p>{FILL}</p><h3>Is it good for gaming?</h3><p>{FILL}</p>",
        "tail": f"<p>{FILL}</p>",
    }
    parts.update(over)
    return "".join(parts.values())


def test_a_good_description_passes():
    assert dw.failures(good(), KP, LINKS) == []


def test_missing_internal_links_are_named():
    html = good().replace('<a href="/gaming-laptop">gaming laptops</a>', "gaming laptops").replace('<a href="/gaming-laptop?brand=Acer">Acer gaming laptops</a>', "Acer gaming laptops")
    assert any("links to 0 of our pages" in f for f in dw.failures(html, KP, LINKS))


def test_a_link_to_an_unknown_page_is_rejected():
    html = good(tail='<p>Buy at <a href="https://www.startech.com.bd/x">another shop</a></p>')
    assert any("ONLY to the allowed URLs" in f for f in dw.failures(html, KP, LINKS))


def test_faq_and_keyphrase_in_heading_are_required():
    no_faq = good(faq="")
    assert any("Frequently Asked Questions" in f for f in dw.failures(no_faq, KP, LINKS))
    no_kp_head = good(h2a=f"<h2>Why it stands out</h2><p><a href=\"/gaming-laptop\">x</a> {FILL}</p>")
    assert any("heading must contain the focus keyphrase" in f for f in dw.failures(no_kp_head, KP, LINKS))


def test_h1_and_short_text_fail():
    assert any("<h1>" in f for f in dw.failures("<h1>Title</h1>" + good(), KP, LINKS))
    assert any("words" in f for f in dw.failures("<p>The Acer Nitro 5.</p>", KP, LINKS))


def test_no_links_known_means_no_link_requirement():
    html = good().replace("<a href=\"/gaming-laptop\">gaming laptops</a>", "gaming laptops").replace("<a href=\"/gaming-laptop?brand=Acer\">Acer gaming laptops</a>", "Acer gaming laptops")
    assert dw.failures(html, KP, []) == []


def test_missing_links_are_appended_as_a_last_resort():
    out = dw._add_missing_links("<p>text</p>", LINKS)
    assert 'href="/gaming-laptop"' in out and 'href="/gaming-laptop?brand=Acer"' in out
    assert dw._add_missing_links(good(), LINKS) == good()  # already linked: untouched


def test_the_category_and_the_brand_link_are_both_required():
    links = [
        {"href": "/hard-disk-drive", "label": "Hard Disk Drive", "kind": "category"},
        {"href": "/toshiba", "label": "Toshiba", "kind": "brand"},
        {"href": "/components", "label": "Components", "kind": "category"},
    ]
    only_cats = good().replace('<a href="/gaming-laptop">gaming laptops</a>', '<a href="/hard-disk-drive">hard disk drive</a>').replace('<a href="/gaming-laptop?brand=Acer">Acer gaming laptops</a>', '<a href="/components">components</a>')
    assert any("must link to /toshiba" in f for f in dw.failures(only_cats, KP, links))
    both = only_cats.replace('<a href="/components">components</a>', '<a href="/toshiba">Toshiba</a>')
    assert dw.failures(both, KP, links) == []
