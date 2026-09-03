"""Shared principal construction used by every identity provider."""

from collections.abc import Mapping

from retpack_core.ports import AccountDirectory
from retpack_core.principal import Principal, Role


def principal_for(directory: AccountDirectory, email: str | None) -> Principal | None:
    """Resolve an email to a ``Principal`` via the directory, or None if unknown.

    An email that is neither internal nor mapped to any account is treated as
    not provisioned and yields None rather than an empty-scope principal.
    """
    if not email or "@" not in email:
        return None
    if directory.is_internal(email):
        return Principal(email=email, account_ids=frozenset(), role=Role.INTERNAL)
    accounts = directory.account_ids_for_email(email)
    if not accounts:
        return None
    return Principal(email=email, account_ids=accounts, role=Role.CUSTOMER)


def header(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup."""
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None
