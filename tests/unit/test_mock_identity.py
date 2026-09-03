import pytest

from retpack_adapters.identity.mock import MockIdentityProvider
from retpack_adapters.mock.directory import FixtureAccountDirectory
from retpack_core.principal import Role

USERS = [
    {"email": "A@dist.com", "account_ids": ["A1", "A2"], "role": "CUSTOMER"},
    {"email": "ops@abi.com", "account_ids": [], "role": "INTERNAL"},
]


@pytest.fixture
def directory() -> FixtureAccountDirectory:
    return FixtureAccountDirectory(USERS)


def test_directory_lookup_is_case_insensitive(directory: FixtureAccountDirectory):
    assert directory.account_ids_for_email("a@DIST.com") == frozenset({"A1", "A2"})
    assert directory.is_internal("OPS@abi.com") is True
    assert directory.account_ids_for_email("nobody@x.com") == frozenset()
    assert directory.is_internal("nobody@x.com") is False


def test_resolve_from_header(directory: FixtureAccountDirectory):
    provider = MockIdentityProvider(directory, default_email=None)
    p = provider.resolve({"X-Forwarded-Email": "a@dist.com"})
    assert p is not None
    assert p.email == "a@dist.com" and p.role is Role.CUSTOMER and p.account_ids == frozenset({"A1", "A2"})


def test_resolve_falls_back_to_default_email(directory: FixtureAccountDirectory):
    provider = MockIdentityProvider(directory, default_email="ops@abi.com")
    p = provider.resolve({})
    assert p is not None and p.role is Role.INTERNAL and p.account_ids == frozenset()


def test_unknown_email_resolves_to_none(directory: FixtureAccountDirectory):
    provider = MockIdentityProvider(directory, default_email="ghost@x.com")
    assert provider.resolve({}) is None


def test_no_identity_at_all_is_none(directory: FixtureAccountDirectory):
    assert MockIdentityProvider(directory, default_email=None).resolve({}) is None


def test_header_beats_default(directory: FixtureAccountDirectory):
    provider = MockIdentityProvider(directory, default_email="ops@abi.com")
    p = provider.resolve({"x-forwarded-email": "a@dist.com"})
    assert p is not None and p.email == "a@dist.com"


def test_directory_rejects_bad_role():
    with pytest.raises(ValueError):
        FixtureAccountDirectory([{"email": "x@y.com", "account_ids": [], "role": "ADMIN"}])


def test_directory_lists_all_provisioned_emails(directory: FixtureAccountDirectory):
    assert directory.list_emails() == ("a@dist.com", "ops@abi.com")
