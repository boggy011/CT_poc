"""Identity for Databricks Apps.

The platform forwards the signed-in user's access token. Rather than trusting
the ``X-Forwarded-Email`` header (client-influenced), the email is obtained by
asking Databricks who the token belongs to. Falling back to the email header
is possible but off by default (``trust_forwarded_email``).
"""

import hashlib
import logging
import time
from collections.abc import Mapping
from typing import Any, Protocol

from retpack_adapters.identity.common import header, principal_for
from retpack_core.ports import AccountDirectory
from retpack_core.principal import Principal

logger = logging.getLogger(__name__)

FORWARDED_TOKEN = "X-Forwarded-Access-Token"
FORWARDED_EMAIL = "X-Forwarded-Email"
TOKEN_CACHE_TTL_S = 300


class TokenIdentityLookup(Protocol):
    """Resolves a bearer token to the platform's notion of its owner."""

    def email_for_token(self, token: str) -> str | None:
        """Email of the token owner, or None if the token is invalid."""
        ...


class SdkTokenIdentityLookup:
    """Calls ``current_user.me()`` with the forwarded token."""

    def __init__(self, host: str, workspace_client_factory: Any = None) -> None:
        self._host = host
        self._factory = workspace_client_factory or _default_factory

    def email_for_token(self, token: str) -> str | None:
        """See ``TokenIdentityLookup.email_for_token``."""
        try:
            user = self._factory(self._host, token).current_user.me()
        except Exception as exc:  # any failure means we do not know who this is
            logger.warning("token identity lookup failed: %s", type(exc).__name__)
            return None
        email = getattr(user, "user_name", None)
        return str(email) if email else None


def _default_factory(host: str, token: str) -> Any:
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(host=host, token=token, auth_type="pat")


class DatabricksAppsIdentityProvider:
    """``IdentityProvider`` for the deployed app."""

    def __init__(self, directory: AccountDirectory, lookup: TokenIdentityLookup, *, trust_forwarded_email: bool = False) -> None:
        self._directory = directory
        self._lookup = lookup
        self._trust_email = trust_forwarded_email
        self._cache: dict[str, tuple[float, str | None]] = {}

    def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        """Resolve from the verified token; optionally from the email header."""
        token = header(headers, FORWARDED_TOKEN)
        email = self._email_for(token) if token else None
        if email is None and self._trust_email:
            email = header(headers, FORWARDED_EMAIL)
        return principal_for(self._directory, email)

    def _email_for(self, token: str) -> str | None:
        key = hashlib.sha256(token.encode()).hexdigest()
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        email = self._lookup.email_for_token(token)
        self._cache[key] = (now + TOKEN_CACHE_TTL_S, email)
        if len(self._cache) > 1000:
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        return email
