"""Load and fail-fast validate a field specification YAML."""

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from retpack_core.config_io import read_yaml
from retpack_core.errors import ConfigError
from retpack_core.fieldspec.schema import FormSpec


def parse_form_spec(data: Any) -> FormSpec:
    """Build a ``FormSpec`` from already-parsed YAML data.

    Args:
        data: Mapping with ``version``, ``sections`` and ``fields`` keys.

    Returns:
        Validated, ordered form specification.

    Raises:
        ConfigError: If the data is not a mapping or violates the schema.
    """
    if not isinstance(data, dict):
        raise ConfigError("field spec must be a mapping with 'version', 'sections' and 'fields'")
    try:
        return FormSpec.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid field spec: {_summarise(exc)}") from exc


def load_form_spec(path: Path) -> FormSpec:
    """Read a YAML file and parse it into a ``FormSpec``.

    Raises:
        ConfigError: If the file is missing, unreadable, or invalid.
    """
    return parse_form_spec(read_yaml(path))


def _summarise(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        msg = err["msg"]
        if err["type"] == "extra_forbidden":
            msg = "extra key not permitted"
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)
