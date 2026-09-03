from io import BytesIO

import pytest

from retpack_core.errors import ConcurrencyConflictError, NotFoundError, NotPermittedError, StateError, ValidationFailedError
from retpack_core.events import EventType
from retpack_core.models import Status
from retpack_core.services import IntakeService, ReviewService, UploadedPdf
from tests.unit.conftest import CUSTOMER_A, CUSTOMER_B, INTERNAL, VALID_VALUES


@pytest.fixture
def submitted(intake: IntakeService):
    return intake.submit(CUSTOMER_A, VALID_VALUES, [UploadedPdf(doc_type="delivery_note", filename="dn.pdf", stream=BytesIO(b"%PDF-1.7"))]).submission


def test_overwrite_appends_event_with_prior_and_new(review: ReviewService, ports, submitted):
    sub = review.overwrite_field(INTERNAL, submitted.submission_id, field="quantity", new_value="15", expected_seq=1)
    assert sub.values["quantity"] == 15
    assert sub.original_values["quantity"] == 12
    assert sub.seq == 2
    ow = sub.overwrites[0]
    assert (ow.field, ow.prior, ow.new, ow.actor) == ("quantity", 12, 15, "ops@abi.com")
    events = ports.submissions.get_events(INTERNAL, submitted.submission_id)
    assert events[-1].event_type is EventType.FIELD_OVERWRITTEN
    assert events[-1].payload == {"field": "quantity", "prior": 12, "new": 15}


def test_overwrite_can_fill_previously_blank_field(review: ReviewService, submitted):
    sub = review.overwrite_field(INTERNAL, submitted.submission_id, field="sales_org", new_value="1000", expected_seq=1)
    assert sub.values["sales_org"] == "1000"
    assert sub.overwrites[0].prior is None


def test_overwrite_validates_format(review: ReviewService, submitted):
    with pytest.raises(ValidationFailedError) as exc:
        review.overwrite_field(INTERNAL, submitted.submission_id, field="container_no", new_value="oops", expected_seq=1)
    assert exc.value.errors == {"container_no": [r"must match ^\d{10}$"]}


def test_overwrite_unknown_field(review: ReviewService, submitted):
    with pytest.raises(ValidationFailedError):
        review.overwrite_field(INTERNAL, submitted.submission_id, field="ghost", new_value="1", expected_seq=1)


def test_overwrite_stale_seq_conflicts(review: ReviewService, submitted):
    review.overwrite_field(INTERNAL, submitted.submission_id, field="quantity", new_value="15", expected_seq=1)
    with pytest.raises(ConcurrencyConflictError):
        review.overwrite_field(INTERNAL, submitted.submission_id, field="quantity", new_value="16", expected_seq=1)


def test_customer_cannot_overwrite(review: ReviewService, submitted):
    with pytest.raises(NotPermittedError):
        review.overwrite_field(CUSTOMER_A, submitted.submission_id, field="quantity", new_value="15", expected_seq=1)


def test_validate_appends_exactly_one_event(review: ReviewService, ports, submitted):
    sub = review.validate(INTERNAL, submitted.submission_id, expected_seq=1)
    assert sub.status is Status.VALIDATED
    assert sub.validated_by == "ops@abi.com"
    events = ports.submissions.get_events(INTERNAL, submitted.submission_id)
    assert [e.event_type for e in events] == [EventType.SUBMITTED, EventType.VALIDATED]


def test_validate_twice_is_state_error(review: ReviewService, submitted):
    review.validate(INTERNAL, submitted.submission_id, expected_seq=1)
    with pytest.raises(StateError):
        review.validate(INTERNAL, submitted.submission_id, expected_seq=2)


def test_overwrite_after_validation_is_state_error(review: ReviewService, submitted):
    review.validate(INTERNAL, submitted.submission_id, expected_seq=1)
    with pytest.raises(StateError):
        review.overwrite_field(INTERNAL, submitted.submission_id, field="quantity", new_value="1", expected_seq=2)


def test_validate_requires_mandatory_fields_present(review: ReviewService, ports, submitted):
    # Simulate a spec tightening after submission: the stored values lack a now-required field.
    from retpack_core.fieldspec import parse_form_spec

    tightened = parse_form_spec(
        {
            "version": 2,
            "sections": [{"name": "s", "label": "S"}],
            "fields": [{"name": "seal_no", "label": "Seal", "type": "string", "section": "s", "order": 1, "required": True}],
        }
    )
    strict_review = ReviewService(ports, tightened)
    with pytest.raises(ValidationFailedError) as exc:
        strict_review.validate(INTERNAL, submitted.submission_id, expected_seq=1)
    assert "seal_no" in exc.value.errors


def test_account_field_cannot_be_overwritten(review: ReviewService, submitted):
    with pytest.raises(ValidationFailedError) as exc:
        review.overwrite_field(INTERNAL, submitted.submission_id, field="account_id", new_value="B1", expected_seq=1)
    assert exc.value.errors == {"account_id": ["cannot be changed"]}
    assert "account_id" not in review.correctable_fields()


def test_dead_letter_can_be_corrected_and_revalidated(review: ReviewService, ports, submitted):
    from retpack_core import events
    from retpack_core.errors import StateError

    sid, acc = submitted.submission_id, submitted.account_id
    review.validate(INTERNAL, sid, expected_seq=1)
    ports.submissions.append_event(INTERNAL, sid, 2, events.cpi_dispatched(sid, acc, seq=3, idempotency_key=f"{sid}:2", attempt=1))
    with pytest.raises(StateError):
        review.overwrite_field(INTERNAL, sid, field="quantity", new_value="1", expected_seq=3)
    ports.submissions.append_event(INTERNAL, sid, 3, events.cpi_failed(sid, acc, seq=4, error="unknown sold-to", attempt=3, terminal=True))
    fixed = review.overwrite_field(INTERNAL, sid, field="bl_no", new_value="BL-78", expected_seq=4)
    assert fixed.status is Status.CPI_FAILED and fixed.values["bl_no"] == "BL-78"
    again = review.validate(INTERNAL, sid, expected_seq=5)
    assert again.status is Status.VALIDATED and again.cpi_error is None and again.validated_seq == 6


def test_review_of_unknown_submission_is_not_found(review: ReviewService):
    with pytest.raises(NotFoundError):
        review.validate(INTERNAL, "0190f0a0-0000-7000-8000-00000000dead", expected_seq=1)


def test_customer_b_cannot_see_a_via_review_path(review: ReviewService, submitted):
    with pytest.raises(NotPermittedError):
        review.validate(CUSTOMER_B, submitted.submission_id, expected_seq=1)
