"""Pydantic schema for the field specification YAML."""

from decimal import Decimal
from enum import StrEnum
from typing import Self

import regex
from pydantic import BaseModel, ConfigDict, Field, model_validator

REF_SOURCES: frozenset[str] = frozenset({"my_accounts", "skus_for_account", "sales_orgs"})
"""Dropdown sources the reference repository must be able to resolve."""

MAX_TEXT_LENGTH = 10_000
"""Absolute cap on any string/text field, applied even when ``max_length`` is unset."""
MAX_PATTERN_LENGTH = 1_024
"""Largest ``max_length`` allowed together with a ``pattern`` (bounded regex input)."""

_STATIC_PREFIX = "static:"
_REF_PREFIX = "ref:"


class FieldType(StrEnum):
    """Supported field types."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    ENUM = "enum"
    TEXT = "text"


_TEXTUAL = {FieldType.STRING, FieldType.TEXT}
_NUMERIC = {FieldType.INTEGER, FieldType.DECIMAL}


class SectionSpec(BaseModel):
    """A visual grouping of fields; order is list position in the YAML."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str


class FieldSpec(BaseModel):
    """One intake field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    type: FieldType
    section: str
    order: int
    required: bool = False
    pattern: str | None = None
    max_length: int | None = Field(default=None, ge=1, le=MAX_TEXT_LENGTH)
    min: Decimal | None = None
    max: Decimal | None = None
    scale: int | None = Field(default=None, ge=0, le=10)
    source: str | None = None
    help: str | None = None

    @model_validator(mode="after")
    def _check_rules_match_type(self) -> Self:
        self._check_text_rules()
        self._check_numeric_rules()
        if self.type is FieldType.ENUM:
            self._check_source()
        elif self.source is not None:
            raise ValueError(f"field {self.name}: source is only valid for enum fields")
        return self

    def _check_text_rules(self) -> None:
        if self.pattern is not None:
            if self.type not in _TEXTUAL:
                raise ValueError(f"field {self.name}: pattern is only valid for string/text fields")
            try:
                regex.compile(self.pattern)
            except regex.error as exc:
                raise ValueError(f"field {self.name}: invalid regex pattern: {exc}") from exc
            if self.max_length is None or self.max_length > MAX_PATTERN_LENGTH:
                raise ValueError(f"field {self.name}: a pattern requires max_length <= {MAX_PATTERN_LENGTH}")
        if self.max_length is not None and self.type not in _TEXTUAL:
            raise ValueError(f"field {self.name}: max_length is only valid for string/text fields")

    def _check_numeric_rules(self) -> None:
        if (self.min is not None or self.max is not None) and self.type not in _NUMERIC:
            raise ValueError(f"field {self.name}: min/max are only valid for integer/decimal fields")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"field {self.name}: min {self.min} is greater than max {self.max}")
        if self.scale is not None and self.type is not FieldType.DECIMAL:
            raise ValueError(f"field {self.name}: scale is only valid for decimal fields")

    def _check_source(self) -> None:
        if not self.source:
            raise ValueError(f"field {self.name}: enum fields need a source")
        if self.source.startswith(_STATIC_PREFIX):
            if not self.static_options:
                raise ValueError(f"field {self.name}: static source has no options")
        elif self.source.startswith(_REF_PREFIX):
            if self.ref_source not in REF_SOURCES:
                raise ValueError(f"field {self.name}: unknown ref source {self.ref_source!r}; known: {sorted(REF_SOURCES)}")
        else:
            raise ValueError(f"field {self.name}: source must start with 'static:' or 'ref:'")

    @property
    def static_options(self) -> tuple[str, ...]:
        """Options declared inline via ``static:a,b,c`` (empty for ref sources)."""
        if not self.source or not self.source.startswith(_STATIC_PREFIX):
            return ()
        return tuple(o.strip() for o in self.source[len(_STATIC_PREFIX) :].split(",") if o.strip())

    @property
    def ref_source(self) -> str | None:
        """Reference-repository source name for ``ref:`` enums, else None."""
        if not self.source or not self.source.startswith(_REF_PREFIX):
            return None
        return self.source[len(_REF_PREFIX) :]

    @property
    def is_textual(self) -> bool:
        """True for string and text fields."""
        return self.type in _TEXTUAL

    @property
    def effective_max_length(self) -> int:
        """``max_length`` or the absolute cap."""
        return self.max_length if self.max_length is not None else MAX_TEXT_LENGTH

    @property
    def effective_scale(self) -> int:
        """Decimal places stored for decimal fields (default 2)."""
        return self.scale if self.scale is not None else 2


class FormSpec(BaseModel):
    """The whole intake form: ordered sections and fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    sections: tuple[SectionSpec, ...]
    fields: tuple[FieldSpec, ...]

    @model_validator(mode="after")
    def _check_and_sort(self) -> Self:
        section_pos = {s.name: i for i, s in enumerate(self.sections)}
        if len(section_pos) != len(self.sections):
            raise ValueError("duplicate section name")
        seen: set[str] = set()
        for f in self.fields:
            if f.name in seen:
                raise ValueError(f"duplicate field name {f.name!r}")
            seen.add(f.name)
            if f.section not in section_pos:
                raise ValueError(f"field {f.name}: unknown section {f.section!r}")
        ordered = tuple(sorted(self.fields, key=lambda f: (section_pos[f.section], f.order, f.name)))
        object.__setattr__(self, "fields", ordered)
        return self

    def field(self, name: str) -> FieldSpec:
        """Return the field spec with this name.

        Raises:
            KeyError: If no field has that name.
        """
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(name)

    def fields_in(self, section: str) -> tuple[FieldSpec, ...]:
        """Fields belonging to one section, in display order."""
        return tuple(f for f in self.fields if f.section == section)

    @property
    def account_field(self) -> FieldSpec | None:
        """The field that selects the owning account (``ref:my_accounts``), if any."""
        return next((f for f in self.fields if f.ref_source == "my_accounts"), None)
