"""Resolved caller identity.

A ``Principal`` is produced by the platform identity adapter on every request
and is the first argument of every repository method. It is never built from
client-supplied input.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    """Portal role."""

    CUSTOMER = "CUSTOMER"
    INTERNAL = "INTERNAL"
    SYSTEM = "SYSTEM"
    """Background jobs (e.g. CPI dispatch). Unscoped like INTERNAL, never a signed-in user."""


@dataclass(frozen=True)
class Principal:
    """Authenticated caller with their resolved account scope.

    Attributes:
        email: Normalised (lower-cased, stripped) sign-in email.
        account_ids: Payer / sold-to codes the caller may see. Empty for
            internal users, who are not account-scoped.
        role: Portal role.
    """

    email: str
    account_ids: frozenset[str] = field(default_factory=frozenset)
    role: Role = Role.CUSTOMER

    def __post_init__(self) -> None:
        """Normalise email and coerce account ids to a frozenset."""
        email = self.email.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("Principal email must be a non-empty address")
        object.__setattr__(self, "email", email)
        object.__setattr__(self, "account_ids", _to_frozenset(self.account_ids))

    @property
    def is_internal(self) -> bool:
        """True for the internal ABI team role."""
        return self.role is Role.INTERNAL

    @property
    def is_scoped(self) -> bool:
        """True when repository reads must be filtered to ``account_ids``."""
        return self.role is Role.CUSTOMER


def _to_frozenset(values: Iterable[str]) -> frozenset[str]:
    return frozenset(str(v) for v in values)
