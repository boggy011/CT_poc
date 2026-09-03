"""Server-side validation of submitted values against a ``FormSpec``.

The portal enforces only mandatory-field and per-field format rules (FR-06).
Returned values are JSON-safe primitives: str for string/text/enum/decimal,
int for integer, ISO ``YYYY-MM-DD`` str for date.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from retpack_core.fieldspec.schema import FieldSpec, FieldType, FormSpec

JsonValue = str | int


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one set of submitted values.

    Attributes:
        values: Cleaned, coerced values for fields that were present and valid.
        errors: Field name to list of messages; empty when ``ok``.
    """

    values: dict[str, JsonValue] = field(default_factory=dict)
    errors: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True when no field produced an error."""
        return not self.errors


def validate_values(
    values: Mapping[str, Any],
    spec: FormSpec,
    *,
    enum_options: Mapping[str, Sequence[str]] | None = None,
) -> ValidationResult:
    """Validate ``values`` against ``spec``.

    Args:
        values: Raw submitted values keyed by field name.
        spec: The form specification.
        enum_options: Allowed options for ``ref:`` enum fields, keyed by field
            name. A ref enum with no supplied options fails closed.

    Returns:
        A ``ValidationResult``; check ``ok`` before using ``values``.
    """
    options = enum_options or {}
    cleaned: dict[str, JsonValue] = {}
    errors: dict[str, list[str]] = {}
    known = {f.name for f in spec.fields}

    for name in values:
        if name not in known:
            errors[name] = ["unknown field"]

    for f in spec.fields:
        value, message = validate_field(f, values.get(f.name), options=options.get(f.name, ()))
        if message is not None:
            errors[f.name] = [message]
        elif value is not None:
            cleaned[f.name] = value

    return ValidationResult(values=cleaned, errors=errors)


def validate_field(f: FieldSpec, raw: Any, *, options: Sequence[str] = ()) -> tuple[JsonValue | None, str | None]:
    """Validate one raw value against one field.

    Returns:
        ``(value, None)`` on success where ``value`` is the coerced value, or
        ``None`` for a blank optional field; ``(None, message)`` on failure.
    """
    if _is_blank(raw):
        return (None, "required") if f.required else (None, None)
    return _coerce(f, raw, options)


def _is_blank(raw: Any) -> bool:
    return raw is None or (isinstance(raw, str) and not raw.strip())


def _coerce(f: FieldSpec, raw: Any, allowed: Sequence[str]) -> tuple[JsonValue | None, str | None]:
    if f.type in (FieldType.STRING, FieldType.TEXT):
        return _coerce_text(f, raw)
    if f.type is FieldType.INTEGER:
        return _coerce_integer(f, raw)
    if f.type is FieldType.DECIMAL:
        return _coerce_decimal(f, raw)
    if f.type is FieldType.DATE:
        return _coerce_date(raw)
    return _coerce_enum(f, raw, allowed)


def _coerce_text(f: FieldSpec, raw: Any) -> tuple[str | None, str | None]:
    text = str(raw).strip()
    if f.max_length is not None and len(text) > f.max_length:
        return None, f"must be at most {f.max_length} characters"
    if f.pattern is not None and re.fullmatch(f.pattern, text) is None:
        return None, f"must match {f.pattern}"
    return text, None


def _coerce_integer(f: FieldSpec, raw: Any) -> tuple[int | None, str | None]:
    if isinstance(raw, bool):
        return None, "must be an integer"
    if isinstance(raw, int):
        number = raw
    else:
        text = str(raw).strip()
        if not re.fullmatch(r"[+-]?\d+", text):
            return None, "must be an integer"
        number = int(text)
    message = _range_error(f, Decimal(number))
    return (None, message) if message else (number, None)


def _coerce_decimal(f: FieldSpec, raw: Any) -> tuple[str | None, str | None]:
    try:
        number = Decimal(str(raw).strip())
    except InvalidOperation:
        return None, "must be a number"
    if not number.is_finite():
        return None, "must be a number"
    message = _range_error(f, number)
    return (None, message) if message else (str(number), None)


def _range_error(f: FieldSpec, number: Decimal) -> str | None:
    if f.min is not None and number < f.min:
        return f"must be at least {f.min}"
    if f.max is not None and number > f.max:
        return f"must be at most {f.max}"
    return None


def _coerce_date(raw: Any) -> tuple[str | None, str | None]:
    if isinstance(raw, date):
        return raw.isoformat(), None
    try:
        return date.fromisoformat(str(raw).strip()).isoformat(), None
    except ValueError:
        return None, "must be a date (YYYY-MM-DD)"


def _coerce_enum(f: FieldSpec, raw: Any, allowed: Sequence[str]) -> tuple[str | None, str | None]:
    text = str(raw).strip()
    choices = f.static_options if f.static_options else tuple(allowed)
    if text not in choices:
        return None, "must be one of the offered options"
    return text, None
