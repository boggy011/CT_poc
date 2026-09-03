"""Identity resolution.

These ports *produce* principals and so are the only ones that do not take one.
"""

from collections.abc import Mapping
from typing import Protocol

from retpack_core.principal import Principal


class AccountDirectory(Protocol):
    """Email to account / role lookup, resolved server-side on every request (FR-01)."""

    def account_ids_for_email(self, email: str) -> frozenset[str]:
        """Accounts a customer email is mapped to; empty if unknown."""
        ...

    def is_internal(self, email: str) -> bool:
        """True if the email belongs to the internal ABI team."""
        ...


class IdentityProvider(Protocol):
    """Turns platform-supplied request context into a ``Principal``."""

    def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        """Resolve the signed-in principal from platform headers.

        Returns:
            The principal, or None if no trusted identity is present.
        """
        ...
