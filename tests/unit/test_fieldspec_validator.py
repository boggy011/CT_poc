from pathlib import Path

import pytest

from retpack_core.fieldspec import load_form_spec, validate_values

SPEC = load_form_spec(Path("config/fields/placeholder.yaml"))

OPTIONS = {
    "account_id": ["A1", "A2"],
    "sku_code": ["KEG50", "KEG30"],
    "sales_org": ["1000", "2000"],
}

VALID = {
    "account_id": "A1",
    "sku_code": "KEG50",
    "sales_org": "1000",
    "container_no": "1234567890",
    "seal_no": "S-1",
    "bl_no": "BL-77",
    "destination": "Antwerp",
    "quantity": "12",
    "weight_tons": "1.5",
    "pickup_date": "2026-09-10",
    "remarks": "anything goes\nhere",
}


def test_happy_path_returns_coerced_values():
    result = validate_values(VALID, SPEC, enum_options=OPTIONS)
    assert result.ok, result.errors
    assert result.values["quantity"] == 12
    assert result.values["weight_tons"] == "1.5"
    assert result.values["pickup_date"] == "2026-09-10"
    assert result.values["container_no"] == "1234567890"


def test_required_missing_and_blank():
    values = {**VALID, "container_no": "   "}
    del values["quantity"]
    result = validate_values(values, SPEC, enum_options=OPTIONS)
    assert result.errors["container_no"] == ["required"]
    assert result.errors["quantity"] == ["required"]


def test_optional_blank_is_omitted_not_error():
    values = {**VALID, "seal_no": "", "remarks": None}
    result = validate_values(values, SPEC, enum_options=OPTIONS)
    assert result.ok
    assert "seal_no" not in result.values
    assert "remarks" not in result.values


def test_pattern_mismatch():
    result = validate_values({**VALID, "container_no": "12345"}, SPEC, enum_options=OPTIONS)
    assert result.errors["container_no"] == [r"must match ^\d{10}$"]


def test_max_length():
    result = validate_values({**VALID, "seal_no": "x" * 21}, SPEC, enum_options=OPTIONS)
    assert result.errors["seal_no"] == ["must be at most 20 characters"]


@pytest.mark.parametrize(
    "bad,msg", [("abc", "must be an integer"), ("1.5", "must be an integer"), ("0", "must be at least 1"), ("10001", "must be at most 10000")]
)
def test_integer_rules(bad: str, msg: str):
    result = validate_values({**VALID, "quantity": bad}, SPEC, enum_options=OPTIONS)
    assert result.errors["quantity"] == [msg]


@pytest.mark.parametrize("bad,msg", [("heavy", "must be a number"), ("-1", "must be at least 0")])
def test_decimal_rules(bad: str, msg: str):
    result = validate_values({**VALID, "weight_tons": bad}, SPEC, enum_options=OPTIONS)
    assert result.errors["weight_tons"] == [msg]


def test_date_rules():
    result = validate_values({**VALID, "pickup_date": "10/09/2026"}, SPEC, enum_options=OPTIONS)
    assert result.errors["pickup_date"] == ["must be a date (YYYY-MM-DD)"]


def test_static_enum_membership():
    result = validate_values({**VALID, "destination": "Atlantis"}, SPEC, enum_options=OPTIONS)
    assert result.errors["destination"] == ["must be one of the offered options"]


def test_ref_enum_membership_uses_supplied_options():
    result = validate_values({**VALID, "sku_code": "KEG99"}, SPEC, enum_options=OPTIONS)
    assert result.errors["sku_code"] == ["must be one of the offered options"]


def test_ref_enum_without_options_fails_closed():
    result = validate_values(VALID, SPEC, enum_options={})
    assert result.errors["sku_code"] == ["must be one of the offered options"]


def test_unknown_field_rejected():
    result = validate_values({**VALID, "hacker": "1"}, SPEC, enum_options=OPTIONS)
    assert result.errors["hacker"] == ["unknown field"]
    assert "hacker" not in result.values


def test_free_text_accepts_anything_within_length():
    result = validate_values({**VALID, "remarks": "🍺 <script>ok</script>"}, SPEC, enum_options=OPTIONS)
    assert result.ok


def test_strings_are_stripped():
    result = validate_values({**VALID, "bl_no": "  BL-77 "}, SPEC, enum_options=OPTIONS)
    assert result.values["bl_no"] == "BL-77"


def test_native_types_accepted():
    from datetime import date
    from decimal import Decimal

    values = {**VALID, "quantity": 5, "weight_tons": Decimal("2.25"), "pickup_date": date(2026, 9, 11)}
    result = validate_values(values, SPEC, enum_options=OPTIONS)
    assert result.ok
    assert result.values["quantity"] == 5
    assert result.values["weight_tons"] == "2.25"
    assert result.values["pickup_date"] == "2026-09-11"
