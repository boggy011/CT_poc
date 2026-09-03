"""Configuration-driven intake fields.

Fields are configuration, not code (FR-03). A YAML file drives the form
renderer, client-side hints and server-side validation from one source.
"""

from retpack_core.fieldspec.loader import load_form_spec, parse_form_spec
from retpack_core.fieldspec.schema import REF_SOURCES, FieldSpec, FieldType, FormSpec, SectionSpec
from retpack_core.fieldspec.validator import ValidationResult, validate_field, validate_values

__all__ = [
    "REF_SOURCES",
    "FieldSpec",
    "FieldType",
    "FormSpec",
    "SectionSpec",
    "ValidationResult",
    "load_form_spec",
    "parse_form_spec",
    "validate_field",
    "validate_values",
]
