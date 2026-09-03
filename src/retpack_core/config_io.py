"""Shared YAML reading with fail-fast errors."""

from pathlib import Path
from typing import Any

import yaml

from retpack_core.errors import ConfigError


def read_yaml(path: Path) -> Any:
    """Read and parse one YAML file.

    Raises:
        ConfigError: If the file cannot be read or is not valid YAML.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
