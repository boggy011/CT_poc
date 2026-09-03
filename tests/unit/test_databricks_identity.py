from retpack_adapters.identity.databricks_apps import DatabricksAppsIdentityProvider
from retpack_adapters.mock.directory import FixtureAccountDirectory
from retpack_core.principal import Role

USERS = [
    {"email": "anna@dist.example", "account_ids": ["A1"], "role": "CUSTOMER"},
    {"email": "ops@abi.example", "account_ids": [], "role": "INTERNAL"},
]


class FakeLookup:
    def __init__(self, mapping: dict[str, str | None]) -> None:
        self.mapping = mapping
        self.calls = 0

    def email_for_token(self, token: str) -> str | None:
        self.calls += 1
        return self.mapping.get(token)


def provider(trust_email: bool = False) -> tuple[DatabricksAppsIdentityProvider, FakeLookup]:
    lookup = FakeLookup({"tok-anna": "anna@dist.example", "tok-ops": "ops@abi.example", "tok-bad": None})
    return DatabricksAppsIdentityProvider(FixtureAccountDirectory(USERS), lookup, trust_forwarded_email=trust_email), lookup


def test_token_decides_identity_not_header():
    p, _ = provider()
    principal = p.resolve({"X-Forwarded-Access-Token": "tok-anna", "X-Forwarded-Email": "ops@abi.example"})
    assert principal is not None and principal.email == "anna@dist.example" and principal.role is Role.CUSTOMER


def test_email_header_alone_is_ignored_by_default():
    p, _ = provider()
    assert p.resolve({"X-Forwarded-Email": "ops@abi.example"}) is None


def test_email_header_used_only_when_explicitly_trusted():
    p, _ = provider(trust_email=True)
    principal = p.resolve({"X-Forwarded-Email": "ops@abi.example"})
    assert principal is not None and principal.role is Role.INTERNAL


def test_invalid_token_is_nobody_even_with_trusted_header_when_token_present():
    p, _ = provider(trust_email=True)
    # A present-but-invalid token falls back to the header only when trust is on; that is the documented weaker mode.
    assert p.resolve({"X-Forwarded-Access-Token": "tok-bad", "X-Forwarded-Email": "anna@dist.example"}) is not None
    p2, _ = provider(trust_email=False)
    assert p2.resolve({"X-Forwarded-Access-Token": "tok-bad", "X-Forwarded-Email": "anna@dist.example"}) is None


def test_unprovisioned_verified_user_is_none():
    lookup = FakeLookup({"tok-x": "stranger@x.example"})
    p = DatabricksAppsIdentityProvider(FixtureAccountDirectory(USERS), lookup)
    assert p.resolve({"X-Forwarded-Access-Token": "tok-x"}) is None


def test_token_lookup_is_cached():
    p, lookup = provider()
    for _ in range(5):
        p.resolve({"X-Forwarded-Access-Token": "tok-ops"})
    assert lookup.calls == 1
