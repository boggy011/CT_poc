"""Identity for local runs: a forwarded-email header if present, else ``RETPACK_MOCK_USER``.

This provider trusts client-supplied headers by design and must never be
constructed for a non-mock backend; ``build_container`` guarantees that.
"""

from collections.abc import Mapping

from retpack_adapters.identity.common import header, principal_for
from retpack_core.ports import AccountDirectory
from retpack_core.principal import Principal

FORWARDED_EMAIL = "X-Forwarded-Email"


class MockIdentityProvider:
    """``IdentityProvider`` for demos: whoever the header or env var says."""

    def __init__(self, directory: AccountDirectory, *, default_email: str | None) -> None:
        self._directory = directory
        self._default = default_email

    def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        """Resolve from the forwarded header, then the default email."""
        email = header(headers, FORWARDED_EMAIL) or self._default
        return principal_for(self._directory, email)
