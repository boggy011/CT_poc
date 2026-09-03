from io import BytesIO

import pytest

from retpack_core.errors import NotFoundError
from retpack_core.models import Status
from retpack_core.services import IntakeService, QueryService, ReviewService, UploadedPdf
from tests.unit.conftest import CUSTOMER_A, CUSTOMER_B, INTERNAL, VALID_VALUES


@pytest.fixture
def three(intake: IntakeService, review: ReviewService):
    a1 = intake.submit(CUSTOMER_A, VALID_VALUES, [UploadedPdf(doc_type="delivery_note", filename="dn.pdf", stream=BytesIO(b"%PDF-1.7"))]).submission
    b1 = intake.submit(CUSTOMER_B, {**VALID_VALUES, "account_id": "B1", "sku_code": "KEG20"}, []).submission
    review.validate(INTERNAL, b1.submission_id, expected_seq=1)
    return a1, b1


def test_list_is_scoped_to_principal(query: QueryService, three):
    a1, b1 = three
    assert [s.submission_id for s in query.list_requests(CUSTOMER_A)] == [a1.submission_id]
    assert [s.submission_id for s in query.list_requests(CUSTOMER_B)] == [b1.submission_id]
    assert {s.submission_id for s in query.list_requests(INTERNAL)} == {a1.submission_id, b1.submission_id}


def test_list_filters_by_status(query: QueryService, three):
    _, b1 = three
    assert [s.submission_id for s in query.list_requests(INTERNAL, status=Status.VALIDATED)] == [b1.submission_id]
    assert query.list_requests(CUSTOMER_A, status=Status.VALIDATED) == ()


def test_get_other_tenant_is_not_found(query: QueryService, three):
    a1, _ = three
    with pytest.raises(NotFoundError):
        query.get_request(CUSTOMER_B, a1.submission_id)
    assert query.get_request(CUSTOMER_A, a1.submission_id).submission_id == a1.submission_id


def test_keg_balances_only_for_my_accounts(query: QueryService):
    bal = query.keg_balances(CUSTOMER_A)
    assert {b.account_id for b in bal} == {"A1"}  # A2 has no balance row yet
    assert bal[0].balance == 40
    assert {b.account_id for b in query.keg_balances(INTERNAL)} == {"A1", "B1"}


def test_open_attachment_checks_scope_first(query: QueryService, three, store):
    a1, _ = three
    with query.open_attachment(CUSTOMER_A, a1.submission_id, seq=1) as f:
        assert f.read() == b"%PDF-1.7"
    with pytest.raises(NotFoundError):
        query.open_attachment(CUSTOMER_B, a1.submission_id, seq=1)
    with pytest.raises(NotFoundError):
        query.open_attachment(CUSTOMER_A, a1.submission_id, seq=9)
