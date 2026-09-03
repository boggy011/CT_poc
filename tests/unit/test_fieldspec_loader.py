from pathlib import Path

import pytest

from retpack_core.errors import ConfigError
from retpack_core.fieldspec import FieldType, load_form_spec, parse_form_spec

PLACEHOLDER = Path("config/fields/placeholder.yaml")

MINIMAL = {
    "version": 1,
    "sections": [{"name": "shipment", "label": "Shipment"}],
    "fields": [
        {
            "name": "container_no",
            "label": "Container number",
            "type": "string",
            "section": "shipment",
            "order": 10,
            "required": True,
            "pattern": r"^\d{10}$",
            "max_length": 10,
        },
    ],
}


def test_placeholder_spec_loads_and_covers_every_type():
    spec = load_form_spec(PLACEHOLDER)
    types = {f.type for f in spec.fields}
    assert types == set(FieldType)
    assert any(f.required for f in spec.fields)
    assert any(f.pattern for f in spec.fields)
    assert any(f.max_length for f in spec.fields)
    assert any(f.min is not None for f in spec.fields)
    assert any(f.source and f.source.startswith("ref:") for f in spec.fields)
    assert any(f.source and f.source.startswith("static:") for f in spec.fields)


def test_fields_ordered_by_section_then_order():
    spec = load_form_spec(PLACEHOLDER)
    section_pos = {s.name: i for i, s in enumerate(spec.sections)}
    keys = [(section_pos[f.section], f.order) for f in spec.fields]
    assert keys == sorted(keys)


def test_field_lookup_by_name():
    spec = parse_form_spec(MINIMAL)
    assert spec.field("container_no").label == "Container number"
    with pytest.raises(KeyError):
        spec.field("nope")


def _with(**field_overrides: object) -> dict:
    data = {**MINIMAL, "fields": [{**MINIMAL["fields"][0], **field_overrides}]}
    return data


def test_unknown_key_rejected():
    with pytest.raises(ConfigError, match="extra"):
        parse_form_spec(_with(colour="red"))


def test_duplicate_name_rejected():
    data = {**MINIMAL, "fields": [MINIMAL["fields"][0], MINIMAL["fields"][0]]}
    with pytest.raises(ConfigError, match="duplicate"):
        parse_form_spec(data)


def test_unknown_section_rejected():
    with pytest.raises(ConfigError, match="section"):
        parse_form_spec(_with(section="ghost"))


def test_enum_requires_source():
    with pytest.raises(ConfigError, match="source"):
        parse_form_spec(_with(type="enum", pattern=None, max_length=None))


def test_unknown_ref_source_rejected():
    with pytest.raises(ConfigError, match="ref source"):
        parse_form_spec(_with(type="enum", pattern=None, max_length=None, source="ref:unicorns"))


def test_static_source_must_have_options():
    with pytest.raises(ConfigError, match="static"):
        parse_form_spec(_with(type="enum", pattern=None, max_length=None, source="static:"))


def test_pattern_only_on_string_types():
    with pytest.raises(ConfigError, match="pattern"):
        parse_form_spec(_with(type="integer", max_length=None))


def test_invalid_regex_rejected():
    with pytest.raises(ConfigError, match="regex"):
        parse_form_spec(_with(pattern="(unclosed"))


def test_min_max_only_on_numeric_types():
    with pytest.raises(ConfigError, match="min"):
        parse_form_spec(_with(pattern=None, max_length=None, min=1))


def test_pattern_requires_bounded_max_length():
    with pytest.raises(ConfigError, match="max_length"):
        parse_form_spec(_with(max_length=None))
    with pytest.raises(ConfigError, match="max_length"):
        parse_form_spec(_with(max_length=5000))


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"type": "integer", "pattern": None, "max_length": None, "min": 100, "max": 1}, "greater than max"),
        ({"type": "integer", "pattern": None, "max_length": 5}, "max_length"),
        ({"type": "integer", "pattern": None, "max_length": None, "scale": 2}, "scale"),
        ({"type": "string", "pattern": None, "max_length": 5, "source": "static:a"}, "source"),
        ({"type": "enum", "pattern": None, "max_length": None, "source": "csv:a,b"}, "static:"),
        ({"type": "text", "pattern": None, "max_length": 100000}, "less than or equal"),
        ({"type": "decimal", "pattern": None, "max_length": None, "scale": 11}, "less than or equal"),
    ],
)
def test_config_guard_rails(overrides: dict, match: str):
    with pytest.raises(ConfigError, match=match):
        parse_form_spec(_with(**overrides))


def test_duplicate_section_rejected():
    data = {**MINIMAL, "sections": [MINIMAL["sections"][0], MINIMAL["sections"][0]]}
    with pytest.raises(ConfigError, match="duplicate section"):
        parse_form_spec(data)


def test_account_field_is_discoverable():
    assert load_form_spec(PLACEHOLDER).account_field is not None
    assert parse_form_spec(MINIMAL).account_field is None


def test_bad_field_name_rejected():
    with pytest.raises(ConfigError):
        parse_form_spec(_with(name="Container No"))


def test_missing_file_is_config_error(tmp_path: Path):
    with pytest.raises(ConfigError):
        load_form_spec(tmp_path / "nope.yaml")


def test_non_mapping_yaml_is_config_error(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a list\n")
    with pytest.raises(ConfigError):
        load_form_spec(p)
