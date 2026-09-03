"""FR-02 release gate: a customer sees only their own data. Parametrized over backends."""

import pytest

from retpack_core import events
from retpack_core.errors import NotFoundError
from retpack_core.ids import new_id
from retpack_core.models import Status
from retpack_core.ports import ReferenceRepository, SubmissionRepository
from tests.conftest import CUSTOMER_A, CUSTOMER_B, INTERNAL, NOBODY, SYSTEM
from tests.contract.test_submission_repository import create


@pytest.fixture
def seeded(repo: SubmissionRepository) -> dict[str, str]:
    return {"a1": create(repo, CUSTOMER_A, "A1"), "a2": create(repo, CUSTOMER_A, "A2"), "b1": create(repo, CUSTOMER_B, "B1")}


def test_list_is_scoped(repo: SubmissionRepository, seeded: dict[str, str]):
    assert {s.submission_id for s in repo.list_submissions(CUSTOMER_A)} == {seeded["a1"], seeded["a2"]}
    assert {s.submission_id for s in repo.list_submissions(CUSTOMER_B)} == {seeded["b1"]}


def test_list_with_status_filter_is_still_scoped(repo: SubmissionRepository, seeded: dict[str, str]):
    repo.append_event(INTERNAL, seeded["b1"], 1, events.validated(seeded["b1"], "B1", actor=INTERNAL.email, seq=2))
    assert repo.list_submissions(CUSTOMER_A, status=Status.VALIDATED) == ()
    assert [s.submission_id for s in repo.list_submissions(CUSTOMER_B, status=Status.VALIDATED)] == [seeded["b1"]]


def test_get_other_tenant_is_not_found(repo: SubmissionRepository, seeded: dict[str, str]):
    with pytest.raises(NotFoundError):
        repo.get_events(CUSTOMER_B, seeded["a1"])
    with pytest.raises(NotFoundError):
        repo.get_submission(CUSTOMER_B, seeded["a1"])


def test_cross_tenant_error_is_indistinguishable_from_missing(repo: SubmissionRepository, seeded: dict[str, str]):
    with pytest.raises(NotFoundError) as foreign:
        repo.get_events(CUSTOMER_B, seeded["a1"])
    with pytest.raises(NotFoundError) as missing:
        repo.get_events(CUSTOMER_B, new_id())
    assert type(foreign.value) is type(missing.value)
    assert "A1" not in str(foreign.value) and "anna" not in str(foreign.value)


def test_append_to_other_tenant_is_not_found(repo: SubmissionRepository, seeded: dict[str, str]):
    ev = events.field_overwritten(seeded["a1"], "A1", actor=CUSTOMER_B.email, seq=2, field="quantity", prior=1, new=99)
    with pytest.raises(NotFoundError):
        repo.append_event(CUSTOMER_B, seeded["a1"], 1, ev)
    assert len(repo.get_events(INTERNAL, seeded["a1"])) == 1


def test_customer_cannot_create_for_foreign_account(repo: SubmissionRepository):
    sid = new_id()
    with pytest.raises(NotFoundError):
        repo.append_event(CUSTOMER_B, sid, 0, events.submitted(sid, "A1", actor=CUSTOMER_B.email, values={"account_id": "A1"}))
    with pytest.raises(NotFoundError):
        repo.get_events(INTERNAL, sid)


def test_principal_with_two_accounts_sees_both(repo: SubmissionRepository, seeded: dict[str, str]):
    assert repo.get_submission(CUSTOMER_A, seeded["a1"]).account_id == "A1"
    assert repo.get_submission(CUSTOMER_A, seeded["a2"]).account_id == "A2"


def test_principal_with_no_accounts_sees_nothing_and_cannot_create(repo: SubmissionRepository, seeded: dict[str, str]):
    assert repo.list_submissions(NOBODY) == ()
    with pytest.raises(NotFoundError):
        repo.get_events(NOBODY, seeded["a1"])
    sid = new_id()
    with pytest.raises(NotFoundError):
        repo.append_event(NOBODY, sid, 0, events.submitted(sid, "A1", actor=NOBODY.email, values={}))


def test_internal_and_system_see_all(repo: SubmissionRepository, seeded: dict[str, str]):
    for p in (INTERNAL, SYSTEM):
        assert {s.submission_id for s in repo.list_submissions(p)} == set(seeded.values())
        assert repo.get_submission(p, seeded["b1"]).account_id == "B1"


def test_reference_my_accounts_is_scoped(reference: ReferenceRepository):
    assert {a.account_id for a in reference.my_accounts(CUSTOMER_A)} == {"A1", "A2"}
    assert {a.account_id for a in reference.my_accounts(CUSTOMER_B)} == {"B1"}
    assert reference.my_accounts(NOBODY) == ()
    assert len(reference.my_accounts(INTERNAL)) >= 3


def test_reference_skus_and_balance_for_foreign_account_not_found(reference: ReferenceRepository):
    assert reference.skus_for_account(CUSTOMER_B, "B1")
    with pytest.raises(NotFoundError):
        reference.skus_for_account(CUSTOMER_B, "A1")
    with pytest.raises(NotFoundError):
        reference.keg_balance(CUSTOMER_B, "A1")
    assert reference.keg_balance(CUSTOMER_B, "B1") is not None


def test_reference_sales_orgs_are_global(reference: ReferenceRepository):
    assert reference.sales_orgs(NOBODY) == reference.sales_orgs(INTERNAL)
