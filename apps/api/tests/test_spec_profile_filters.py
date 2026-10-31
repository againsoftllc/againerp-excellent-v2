"""Aladin's spec-profile filters: a source shop's category filters land ON the matching spec attributes (no extra group), and the numeric buckets."""
from app.services.catalog_ai import spec_profile_service as sp
from app.services.catalog_ai.scraper import merge_filters

LAPTOP = [
    {"title": "Display Size", "options": ["Below 13-inch", "13-Inch to 13.9-Inch", "16-Inch to 16.9-Inch"]},
    {"title": "RAM Size", "options": ["8 GB", "16 GB", "32 GB"]},
    {"title": "Special Features", "options": ["Backlit Keyboard", "Type-C Port"]},
    {"title": "Too Few", "options": ["Only one"]},
]
PROPOSAL = {
    "name": "Laptop",
    "groups": [
        {"name": "Display", "attributes": ["Display Size", "Resolution"]},
        {"name": "Memory", "attributes": ["RAM", "RAM Type"]},
    ],
}


def test_display_type_is_inferred():
    assert sp.infer_filter_display("Display Size", LAPTOP[0]["options"]) == "range"
    assert sp.infer_filter_display("RAM Size", LAPTOP[1]["options"]) == "single_select"
    assert sp.infer_filter_display("Special Features", LAPTOP[2]["options"]) == "multi_select"


def test_filters_sit_on_the_matching_attributes_and_nothing_is_listed_twice():
    out = sp.attach_source_filters(PROPOSAL, [], LAPTOP)  # no model: names decide
    by_title = {e["title"]: e for e in out["filter_attrs"]}
    assert set(by_title) == {"Display Size", "RAM Size", "Special Features"}  # a one-option filter is dropped
    assert (by_title["Display Size"]["group"], by_title["Display Size"]["attribute"], by_title["Display Size"]["new"]) == ("Display", "Display Size", False)
    assert (by_title["RAM Size"]["group"], by_title["RAM Size"]["attribute"]) == ("Memory", "RAM")  # "RAM Size" is the "RAM" attribute
    assert by_title["RAM Size"]["options"] == ["8 GB", "16 GB", "32 GB"]
    assert by_title["Special Features"]["new"] is True  # no attribute says that: a new one
    assert "Overview" not in [g["name"] for g in out["groups"]]
    labels = [(g["name"], a) for g in out["groups"] for a in g["attributes"]]
    assert len(labels) == len(set(labels))  # no attribute twice in a group
    assert out["ranges"] == ["Display Size"] and out["multi"] == ["Special Features"]
    assert [a for g in out["groups"] if g["name"] == "Display" for a in g["attributes"]] == ["Display Size", "Resolution"]  # nothing else touched


def test_no_filters_leaves_the_proposal_alone():
    out = sp.attach_source_filters(PROPOSAL, [], [])
    assert out["groups"] == PROPOSAL["groups"] and out["filter_attrs"] == []


def test_numeric_bucket():
    field = {"options": ["Below 13-inch", "13-Inch to 13.9-Inch", "16-Inch to 16.9-Inch"]}
    assert sp._bucket_option(field, "16-Inch") == "16-Inch to 16.9-Inch"
    assert sp._bucket_option(field, '13.3"') == "13-Inch to 13.9-Inch"
    assert sp._bucket_option(field, "12.5 Inch") == "Below 13-inch"
    assert sp._bucket_option(field, "18 inch") is None


def test_merge_filters_union_keeps_first_order():
    merged = merge_filters(
        [{"title": "Processor Type", "options": ["Intel", "AMD", "Apple"]}],
        [{"title": "processor type", "options": ["AMD", "Snapdragon"]}, {"title": "Series", "options": ["a", "b"]}],
    )
    assert merged[0]["options"] == ["Intel", "AMD", "Apple", "Snapdragon"] and merged[1]["title"] == "Series"
