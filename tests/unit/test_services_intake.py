from io import BytesIO

import pytest

from retpack_core.errors import NotPermittedError, ValidationFailedError
from retpack_core.events import EventType
from retpack_core.models import Status
from retpack_core.services import IntakeService, UploadedPdf
from tests.unit.conftest import CUSTOMER_A, CUSTOMER_B, INTERNAL, VALID_VALUES


def pdf(name: str = "dn.pdf", body: bytes = b"%PDF-1.7 hello", doc_type: str = "delivery_note") -> UploadedPdf:
    return UploadedPdf(doc_type=doc_type, filename=name, stream=BytesIO(body))


def test_enum_options_resolve_ref_sources(intake: IntakeService):
    opts = intake.enum_options(CUSTOMER_A, account_id="A1")
    assert set(opts["account_id"]) == {"A1", "A2"}
    assert opts["sku_code"] == ("KEG50", "KEG30")
    assert opts["sales_org"] == ("1000", "2000")


def test_enum_options_without_account_has_no_skus(intake: IntakeService):
    opts = intake.enum_options(CUSTOMER_A, account_id=None)
    assert opts["sku_code"] == ()


def test_submit_happy_path_returns_folded_submission_without_round_trip(intake: IntakeService, ports, store):
    result = intake.submit(CUSTOMER_A, VALID_VALUES, [pdf()])
    sub = result.submission
    assert result.warnings == ()
    assert sub.status is Status.SUBMITTED
    assert sub.account_id == "A1"
    assert sub.values["quantity"] == 12
    assert sub.seq == 1
    assert len(sub.attachments) == 1
    assert sub.attachments[0].doc_type == "delivery_note"
    assert store.puts == [("a@dist.com", sub.submission_id, "delivery_note")]
    events = ports.submissions.get_events(CUSTOMER_A, sub.submission_id)
    assert [e.event_type for e in events] == [EventType.SUBMITTED]
    assert events[0].payload["attachments"][0]["sha256"] == sub.attachments[0].sha256


def test_submit_is_one_event_append_even_with_attachments(intake: IntakeService, ports):
    sub = intake.submit(CUSTOMER_A, VALID_VALUES, [pdf("a.pdf"), pdf("b.pdf", b"%PDF-1.7 other", doc_type="other")]).submission
    assert len(ports.submissions.get_events(CUSTOMER_A, sub.submission_id)) == 1
    assert len(sub.attachments) == 2


def test_submit_invalid_values_raises_and_appends_nothing(intake: IntakeService, ports, store):
    with pytest.raises(ValidationFailedError) as exc:
        intake.submit(CUSTOMER_A, {**VALID_VALUES, "container_no": "12"}, [pdf()])
    assert exc.value.errors == {"container_no": [r"must match ^\d{10}$"]}
    assert ports.submissions.list_submissions(INTERNAL) == ()
    assert store.puts == []


def test_submit_for_foreign_account_is_validation_error(intake: IntakeService):
    with pytest.raises(ValidationFailedError) as exc:
        intake.submit(CUSTOMER_B, VALID_VALUES, [pdf()])
    assert "account_id" in exc.value.errors


def test_submit_with_sku_of_other_account_rejected(intake: IntakeService):
    with pytest.raises(ValidationFailedError) as exc:
        intake.submit(CUSTOMER_A, {**VALID_VALUES, "sku_code": "KEG20"}, [pdf()])
    assert exc.value.errors == {"sku_code": ["must be one of the offered options"]}


def test_internal_cannot_submit(intake: IntakeService):
    with pytest.raises(NotPermittedError):
        intake.submit(INTERNAL, VALID_VALUES, [pdf()])


def test_too_many_attachments_rejected(intake: IntakeService):
    with pytest.raises(ValidationFailedError) as exc:
        intake.submit(CUSTOMER_A, VALID_VALUES, [pdf("a.pdf"), pdf("b.pdf", b"%PDF-1.7 x"), pdf("c.pdf", b"%PDF-1.7 y")])
    assert "attachments.delivery_note" in exc.value.errors


def test_unknown_doc_type_rejected(intake: IntakeService):
    bad = UploadedPdf(doc_type="selfie", filename="me.pdf", stream=BytesIO(b"%PDF-1.7"))
    with pytest.raises(ValidationFailedError) as exc:
        intake.submit(CUSTOMER_A, VALID_VALUES, [bad])
    assert "attachments.selfie" in exc.value.errors


def test_duplicate_pdf_within_submission_rejected(intake: IntakeService, store):
    with pytest.raises(ValidationFailedError) as exc:
        intake.submit(CUSTOMER_A, VALID_VALUES, [pdf("a.pdf"), pdf("b.pdf")])
    assert "attachments" in exc.value.errors
    assert store.puts == []


def test_submit_without_attachments_allowed_when_none_required(intake: IntakeService):
    sub = intake.submit(CUSTOMER_A, VALID_VALUES, []).submission
    assert sub.attachments == ()


def test_scanned_pdf_flagged_not_blocked(intake: IntakeService):
    result = intake.submit(CUSTOMER_A, VALID_VALUES, [pdf("scan.pdf", b"%PDF-SCAN")])
    assert result.submission.attachments[0].has_text_layer is False
    assert result.warnings == ("scan.pdf has no text layer; the automated cross-check cannot read it",)
