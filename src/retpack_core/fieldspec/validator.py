"""Server-side validation of submitted values against a ``FormSpec``.

The portal enforces only mandatory-field and per-field format rules (FR-06).
Returned values are JSON-safe primitives: str for string/text/enum, str with a
fixed number of decimals for decimal, int for integer, ISO ``YYYY-MM-DD`` str
for date.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import regex

from retpack_core.fieldspec.schema import FieldSpec, FieldType, FormSpec

JsonValue = str | int

REGEX_TIMEOUT_S = 0.05
"""Upper bound per pattern match; a config-supplied catastrophic regex cannot stall the app."""
MAX_NUMERIC_CHARS = 40
_INTEGER = regex.compile(r"[+-]?\d{1,39}")
_DECIMAL = regex.compile(r"[+-]?\d{1,30}(\.\d{1,10})?")


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
        value, messages = validate_field(f, values.get(f.name), options=options.get(f.name, ()))
        if messages:
            errors[f.name] = messages
        elif value is not None:
            cleaned[f.name] = value

    return ValidationResult(values=cleaned, errors=errors)


def validate_field(f: FieldSpec, raw: Any, *, options: Sequence[str] = ()) -> tuple[JsonValue | None, list[str]]:
    """Validate one raw value against one field.

    Returns:
        ``(value, [])`` on success where ``value`` is the coerced value, or
        ``None`` for a blank optional field; ``(None, messages)`` on failure
        with every violated rule listed.
    """
    if _is_blank(raw):
        return (None, ["required"]) if f.required else (None, [])
    return _coerce(f, raw, options)


def _is_blank(raw: Any) -> bool:
    return raw is None or (isinstance(raw, str) and not raw.strip())


def _coerce(f: FieldSpec, raw: Any, allowed: Sequence[str]) -> tuple[JsonValue | None, list[str]]:
    if f.type in (FieldType.STRING, FieldType.TEXT):
        return _coerce_text(f, raw)
    if f.type is FieldType.INTEGER:
        return _coerce_integer(f, raw)
    if f.type is FieldType.DECIMAL:
        return _coerce_decimal(f, raw)
    if f.type is FieldType.DATE:
        return _coerce_date(raw)
    return _coerce_enum(f, raw, allowed)


def _coerce_text(f: FieldSpec, raw: Any) -> tuple[str | None, list[str]]:
    text = str(raw).strip()
    messages = []
    if len(text) > f.effective_max_length:
        messages.append(f"must be at most {f.effective_max_length} characters")
    if f.pattern is not None and not _matches(f.pattern, text[: f.effective_max_length]):
        messages.append(f"must match {f.pattern}")
    return (None, messages) if messages else (text, [])


def _matches(pattern: str, text: str) -> bool:
    try:
        return regex.fullmatch(pattern, text, timeout=REGEX_TIMEOUT_S) is not None
    except TimeoutError:
        return False


def _coerce_integer(f: FieldSpec, raw: Any) -> tuple[int | None, list[str]]:
    if isinstance(raw, bool):
        return None, ["must be an integer"]
    if isinstance(raw, int):
        number = raw
    else:
        text = str(raw).strip()
        if len(text) > MAX_NUMERIC_CHARS or _INTEGER.fullmatch(text) is None:
            return None, ["must be an integer"]
        number = int(text)
    message = _range_error(f, Decimal(number))
    return (None, [message]) if message else (number, [])


def _coerce_decimal(f: FieldSpec, raw: Any) -> tuple[str | None, list[str]]:
    if isinstance(raw, bool):
        return None, ["must be a number"]
    text = repr(raw) if isinstance(raw, float) else str(raw).strip()
    try:
        number = Decimal(text) if isinstance(raw, float) else _parse_decimal_text(text)
    except (InvalidOperation, ValueError, ArithmeticError):
        return None, ["must be a number"]
    if not number.is_finite():
        return None, ["must be a number"]
    quantised = number.quantize(Decimal(1).scaleb(-f.effective_scale))
    message = _range_error(f, quantised)
    return (None, [message]) if message else (format(quantised, "f"), [])


def _parse_decimal_text(text: str) -> Decimal:
    if len(text) > MAX_NUMERIC_CHARS or _DECIMAL.fullmatch(text) is None:
        raise ValueError(text)
    return Decimal(text)


def _range_error(f: FieldSpec, number: Decimal) -> str | None:
    if f.min is not None and number < f.min:
        return f"must be at least {f.min}"
    if f.max is not None and number > f.max:
        return f"must be at most {f.max}"
    return None


def _coerce_date(raw: Any) -> tuple[str | None, list[str]]:
    if isinstance(raw, datetime):
        return raw.date().isoformat(), []
    if isinstance(raw, date):
        return raw.isoformat(), []
    try:
        return date.fromisoformat(str(raw).strip()).isoformat(), []
    except ValueError:
        return None, ["must be a date (YYYY-MM-DD)"]


def _coerce_enum(f: FieldSpec, raw: Any, allowed: Sequence[str]) -> tuple[str | None, list[str]]:
    text = str(raw).strip()
    choices = f.static_options if f.static_options else tuple(allowed)
    if text not in choices:
        return None, ["must be one of the offered options"]
    return text, []
