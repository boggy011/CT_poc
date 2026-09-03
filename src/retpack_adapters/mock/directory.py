"""Email to account / role directory from a list of user records (``users.json``)."""

from collections.abc import Iterable, Mapping
from typing import Any

from retpack_core.principal import Role


class FixtureAccountDirectory:
    """``AccountDirectory`` over static user records."""

    def __init__(self, users: Iterable[Mapping[str, Any]]) -> None:
        self._accounts: dict[str, frozenset[str]] = {}
        self._internal: set[str] = set()
        for u in users:
            email = str(u["email"]).strip().lower()
            role = Role(str(u.get("role", "CUSTOMER")))
            if role is Role.INTERNAL:
                self._internal.add(email)
            self._accounts[email] = frozenset(str(a) for a in u.get("account_ids", []))

    def account_ids_for_email(self, email: str) -> frozenset[str]:
        """See ``AccountDirectory.account_ids_for_email``."""
        return self._accounts.get(email.strip().lower(), frozenset())

    def is_internal(self, email: str) -> bool:
        """See ``AccountDirectory.is_internal``."""
        return email.strip().lower() in self._internal

    def list_emails(self) -> tuple[str, ...]:
        """See ``AccountDirectory.list_emails``."""
        return tuple(sorted(set(self._accounts) | self._internal))
