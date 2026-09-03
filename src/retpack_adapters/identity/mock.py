"""Identity for local runs: a forwarded-email header if present, else ``RETPACK_MOCK_USER``."""

from collections.abc import Mapping

from retpack_adapters.identity.common import header, principal_for
from retpack_core.ports import AccountDirectory
from retpack_core.principal import Principal

FORWARDED_EMAIL = "X-Forwarded-Email"


class MockIdentityProvider:
    """``IdentityProvider`` with a sidebar-switchable user for demos."""

    def __init__(self, directory: AccountDirectory, *, default_email: str | None) -> None:
        self._directory = directory
        self._default = default_email

    def resolve(self, headers: Mapping[str, str], *, override_email: str | None = None) -> Principal | None:
        """Resolve from ``override_email``, then the forwarded header, then the default."""
        email = override_email or header(headers, FORWARDED_EMAIL) or self._default
        return principal_for(self._directory, email)
