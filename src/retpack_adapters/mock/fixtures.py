"""Load reference data and users from JSON files in the mock data directory."""

import json
from pathlib import Path
from typing import Any

from retpack_adapters.mock.directory import FixtureAccountDirectory
from retpack_adapters.mock.reference import InMemoryReferenceRepository
from retpack_core.errors import ConfigError
from retpack_core.models import Account, KegBalance, SalesOrg, Sku


def _read(path: Path) -> list[Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot load mock data {path}: {exc}") from exc
    if not isinstance(data, list):
        raise ConfigError(f"{path} must contain a JSON list")
    return data


def load_reference(data_dir: Path) -> InMemoryReferenceRepository:
    """Build the reference repository from ``accounts/skus/sales_orgs/balances.json``."""
    return InMemoryReferenceRepository(
        accounts=[Account.model_validate(r) for r in _read(data_dir / "accounts.json")],
        skus=[Sku.model_validate(r) for r in _read(data_dir / "skus.json")],
        sales_orgs=[SalesOrg.model_validate(r) for r in _read(data_dir / "sales_orgs.json")],
        balances=[KegBalance.model_validate(r) for r in _read(data_dir / "balances.json")],
    )


def load_directory(data_dir: Path) -> FixtureAccountDirectory:
    """Build the account directory from ``users.json``."""
    return FixtureAccountDirectory(_read(data_dir / "users.json"))


def list_user_emails(data_dir: Path) -> tuple[str, ...]:
    """Emails in ``users.json``, for the demo user switcher."""
    return tuple(str(u["email"]) for u in _read(data_dir / "users.json"))
