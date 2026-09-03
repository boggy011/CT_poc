import dataclasses

import pytest

from retpack_core.principal import Principal, Role


def test_principal_is_frozen():
    p = Principal(email="a@x.com", account_ids=frozenset({"A1"}), role=Role.CUSTOMER)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.email = "b@x.com"  # type: ignore[misc]


def test_account_ids_coerced_to_frozenset():
    p = Principal(email="a@x.com", account_ids=["A1", "A2", "A1"], role=Role.CUSTOMER)  # type: ignore[arg-type]
    assert p.account_ids == frozenset({"A1", "A2"})
    assert isinstance(p.account_ids, frozenset)


def test_email_is_normalised():
    p = Principal(email="  A@X.com ", account_ids=frozenset(), role=Role.CUSTOMER)
    assert p.email == "a@x.com"


@pytest.mark.parametrize("email", ["", "   ", "not-an-email"])
def test_invalid_email_rejected(email: str):
    with pytest.raises(ValueError):
        Principal(email=email, account_ids=frozenset(), role=Role.CUSTOMER)


def test_is_internal():
    internal = Principal(email="ops@abi.com", account_ids=frozenset(), role=Role.INTERNAL)
    customer = Principal(email="c@dist.com", account_ids=frozenset({"A1"}), role=Role.CUSTOMER)
    assert internal.is_internal is True
    assert customer.is_internal is False


def test_customer_may_have_no_accounts():
    p = Principal(email="c@dist.com", account_ids=frozenset(), role=Role.CUSTOMER)
    assert p.account_ids == frozenset()


def test_system_role_is_unscoped():
    system = Principal(email="cpi-dispatch@system.local", account_ids=frozenset(), role=Role.SYSTEM)
    customer = Principal(email="c@dist.com", account_ids=frozenset({"A1"}), role=Role.CUSTOMER)
    internal = Principal(email="ops@abi.com", account_ids=frozenset(), role=Role.INTERNAL)
    assert system.is_scoped is False
    assert internal.is_scoped is False
    assert customer.is_scoped is True
    assert system.is_internal is False
