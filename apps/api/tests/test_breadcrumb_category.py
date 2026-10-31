"""The category of an imported product comes from the source breadcrumb - never from the product's own title."""
from app.schemas.catalog_ai_import import ProductDraft
from app.services.catalog_ai import importer_service as imp

CRUMBS = ["home", "Component", "Hard Disk Drive", "Toshiba", 'Toshiba S300 2TB 5400rpm 3.5" Surveillance Hard Drive']
LINKS = [
    {"name": "home", "url": "https://www.startech.com.bd/"},
    {"name": "Component", "url": "https://www.startech.com.bd/component"},
    {"name": "Hard Disk Drive", "url": "https://www.startech.com.bd/component/hard-disk-drive"},
    {"name": "Toshiba", "url": "https://www.startech.com.bd/component/hard-disk-drive/toshiba-hdd"},
    {"name": 'Toshiba S300 2TB 5400rpm 3.5" Surveillance Hard Drive', "url": "https://www.startech.com.bd/toshiba-s300-2tb-surveillance-hard-drive"},
]
PAGE = "https://www.startech.com.bd/toshiba-s300-2tb-surveillance-hard-drive"


def _category(name, **kw):
    saved = imp._match_category
    imp._match_category = lambda db, cid, n: None  # none of these categories exists yet
    try:
        return imp._category_from_breadcrumb(None, "default", CRUMBS, ProductDraft(name=name, brand_name="Toshiba", model="S300"), **kw)
    finally:
        imp._match_category = saved


def test_the_deepest_category_crumb_is_the_category_whatever_the_title_says():
    # the AI keeps the title short or long - the shop's own long title must never become a category
    assert _category('Toshiba S300 2TB 5400rpm 3.5" Surveillance Hard Drive') == "Hard Disk Drive"
    assert _category("Toshiba S300 2TB Surveillance Hard Drive") == "Hard Disk Drive"
    assert _category("Toshiba Surveillance HDD", links=LINKS, source_url=PAGE) == "Hard Disk Drive"  # even a very different title: the link is the page itself


def test_a_short_category_name_is_never_taken_for_the_product():
    assert not imp._is_product_crumb("Hard Disk Drive", "Toshiba S300 Hard Disk Drive 2TB")
    assert imp._is_product_crumb('Toshiba S300 2TB 5400rpm 3.5" Surveillance Hard Drive', "Toshiba S300 2TB Surveillance Hard Drive")
