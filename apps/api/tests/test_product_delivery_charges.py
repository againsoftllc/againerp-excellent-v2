from decimal import Decimal

from app.services.ecommerce.checkout_shipping_availability import (
    parse_product_charge_rules,
    product_charge_for_values,
)

RAW = '[{"attribute":"screen_size","charges":{"21-22 inch":100,"26-30 inch":"300","31-40 inch":0,"bad":"x"}}]'


def test_parse_drops_zero_negative_and_non_numeric():
    rules = parse_product_charge_rules(RAW)
    assert rules == [{"attribute": "screen_size", "charges": {"21-22 inch": Decimal("100"), "26-30 inch": Decimal("300")}}]


def test_parse_never_raises_on_bad_input():
    for raw in (None, "", "not json", "{}", "[1, 2]", '[{"attribute": "", "charges": {}}]', '[{"attribute": "x"}]'):
        assert parse_product_charge_rules(raw) == []


def test_charge_matches_value_case_insensitively():
    rules = parse_product_charge_rules(RAW)
    assert product_charge_for_values(rules, {"screen_size": " 26-30 INCH "}) == Decimal("300")
    assert product_charge_for_values(rules, {"screen_size": "21-22 inch"}) == Decimal("100")


def test_no_charge_for_unlisted_missing_or_other_attribute():
    rules = parse_product_charge_rules(RAW)
    assert product_charge_for_values(rules, {"screen_size": "15-17 inch"}) == Decimal("0")
    assert product_charge_for_values(rules, {}) == Decimal("0")
    assert product_charge_for_values(rules, {"capacity": "26-30 inch"}) == Decimal("0")


def test_rules_add_up():
    rules = parse_product_charge_rules(
        '[{"attribute":"a","charges":{"x":10}},{"attribute":"b","charges":{"y":5}}]'
    )
    assert product_charge_for_values(rules, {"a": "x", "b": "y"}) == Decimal("15")
