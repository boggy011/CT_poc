"""Attachment policy: document types, cardinality and size limit as configuration (FR-04)."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from retpack_core.config_io import read_yaml
from retpack_core.errors import ConfigError


class DocTypeSpec(BaseModel):
    """One allowed document type."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    required: bool = False
    max_count: int = Field(default=1, ge=1)


class AttachmentPolicy(BaseModel):
    """Which PDFs may accompany a submission, and how many."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    max_size_mb: int = Field(ge=1)
    max_pages: int = Field(default=500, ge=1)
    inspect_timeout_s: float = Field(default=15.0, gt=0)
    doc_types: tuple[DocTypeSpec, ...]

    @model_validator(mode="after")
    def _unique_names(self) -> Self:
        names = [d.name for d in self.doc_types]
        if len(set(names)) != len(names):
            raise ValueError("duplicate doc_type name")
        return self

    @property
    def max_size_bytes(self) -> int:
        """Per-file size limit in bytes."""
        return self.max_size_mb * 1024 * 1024

    def doc_type(self, name: str) -> DocTypeSpec:
        """Look up one document type.

        Raises:
            KeyError: If unknown.
        """
        for d in self.doc_types:
            if d.name == name:
                return d
        raise KeyError(name)

    def check_counts(self, counts: Mapping[str, int]) -> dict[str, str]:
        """Check per-type counts against cardinality rules.

        Returns:
            Doc-type name to message for every violation; empty when all good.
        """
        errors: dict[str, str] = {}
        known = {d.name for d in self.doc_types}
        for name in counts:
            if name not in known:
                errors[name] = "unknown document type"
        for d in self.doc_types:
            n = counts.get(d.name, 0)
            if d.required and n < 1:
                errors[d.name] = f"at least one {d.name} is required"
            elif n > d.max_count:
                errors[d.name] = f"at most {d.max_count} {d.name} allowed"
        return errors


def parse_attachment_policy(data: Any) -> AttachmentPolicy:
    """Build an ``AttachmentPolicy`` from parsed YAML.

    Raises:
        ConfigError: If the data violates the schema.
    """
    if not isinstance(data, dict):
        raise ConfigError("attachment policy must be a mapping")
    try:
        return AttachmentPolicy.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid attachment policy: {exc}") from exc


def load_attachment_policy(path: Path) -> AttachmentPolicy:
    """Read and parse the attachment policy YAML.

    Raises:
        ConfigError: If the file is missing or invalid.
    """
    return parse_attachment_policy(read_yaml(path))
