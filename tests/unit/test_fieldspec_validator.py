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
    assert result.values["weight_tons"] == "1.50"
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


@pytest.mark.parametrize(
    "bad,msg",
    [("heavy", "must be a number"), ("-1", "must be at least 0"), ("1e5", "must be a number"), ("1_0", "must be a number"), ("9" * 41, "must be a number")],
)
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


def test_float_noise_is_quantised_to_scale():
    result = validate_values({**VALID, "weight_tons": 0.1 + 0.2}, SPEC, enum_options=OPTIONS)
    assert result.values["weight_tons"] == "0.30"
    result = validate_values({**VALID, "weight_tons": 1e-05}, SPEC, enum_options=OPTIONS)
    assert result.values["weight_tons"] == "0.00"


def test_datetime_is_stored_as_date():
    from datetime import UTC, datetime

    result = validate_values({**VALID, "pickup_date": datetime(2026, 9, 3, 14, 30, tzinfo=UTC)}, SPEC, enum_options=OPTIONS)
    assert result.values["pickup_date"] == "2026-09-03"


def test_all_violations_reported_per_field():
    result = validate_values({**VALID, "container_no": "x" * 11}, SPEC, enum_options=OPTIONS)
    assert result.errors["container_no"] == ["must be at most 10 characters", r"must match ^\d{10}$"]


def test_huge_integer_string_is_a_validation_error_not_a_crash():
    result = validate_values({**VALID, "quantity": "9" * 5000}, SPEC, enum_options=OPTIONS)
    assert result.errors["quantity"] == ["must be an integer"]


def test_text_without_max_length_is_still_capped():
    from retpack_core.fieldspec import parse_form_spec
    from retpack_core.fieldspec.schema import MAX_TEXT_LENGTH

    spec = parse_form_spec(
        {"version": 1, "sections": [{"name": "s", "label": "S"}], "fields": [{"name": "t", "label": "T", "type": "text", "section": "s", "order": 1}]}
    )
    result = validate_values({"t": "x" * (MAX_TEXT_LENGTH + 1)}, spec)
    assert result.errors["t"] == [f"must be at most {MAX_TEXT_LENGTH} characters"]


def test_catastrophic_pattern_cannot_stall_validation():
    import time

    from retpack_core.fieldspec import parse_form_spec

    spec = parse_form_spec(
        {
            "version": 1,
            "sections": [{"name": "s", "label": "S"}],
            "fields": [{"name": "t", "label": "T", "type": "string", "section": "s", "order": 1, "pattern": r"^(\w+\s?)*$", "max_length": 64}],
        }
    )
    started = time.perf_counter()
    result = validate_values({"t": "a" * 40 + "!"}, spec)
    assert time.perf_counter() - started < 2
    assert result.errors["t"] == [r"must match ^(\w+\s?)*$"]
