from datetime import UTC, datetime, timedelta

import pytest

from retpack_core import events as ev
from retpack_core.fold import fold
from retpack_core.models import AttachmentMeta, Status

SID = "0190f0a0-0000-7000-8000-000000000001"
T0 = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)


def t(n: int) -> datetime:
    return T0 + timedelta(minutes=n)


def submitted():
    return ev.submitted(SID, "A1", actor="c@d.com", values={"qty": 10, "bl_no": "BL-1"}, seq=1, at=t(0))


def test_empty_log_rejected():
    with pytest.raises(ValueError, match="empty"):
        fold([])


def test_first_event_must_be_submitted():
    with pytest.raises(ValueError, match="SUBMITTED"):
        fold([ev.validated(SID, "A1", actor="o@abi.com", seq=1, at=t(0))])


def test_seq_gap_rejected():
    with pytest.raises(ValueError, match="seq"):
        fold([submitted(), ev.validated(SID, "A1", actor="o@abi.com", seq=3, at=t(1))])


def test_mixed_submission_ids_rejected():
    other = ev.validated("0190f0a0-0000-7000-8000-000000000002", "A1", actor="o@abi.com", seq=2, at=t(1))
    with pytest.raises(ValueError, match="submission_id"):
        fold([submitted(), other])


def test_submitted_only():
    s = fold([submitted()])
    assert s.status is Status.SUBMITTED
    assert s.values == {"qty": 10, "bl_no": "BL-1"}
    assert s.original_values == s.values
    assert s.submitted_by == "c@d.com"
    assert s.submitted_at == t(0)
    assert s.seq == 1
    assert s.account_id == "A1"
    assert s.validated_at is None


def test_overwrite_changes_value_and_keeps_original_and_audit():
    log = [submitted(), ev.field_overwritten(SID, "A1", actor="o@abi.com", seq=2, field="qty", prior=10, new=12, at=t(1))]
    s = fold(log)
    assert s.values["qty"] == 12
    assert s.original_values["qty"] == 10
    assert len(s.overwrites) == 1
    ow = s.overwrites[0]
    assert (ow.field, ow.prior, ow.new, ow.actor, ow.occurred_at) == ("qty", 10, 12, "o@abi.com", t(1))
    assert s.status is Status.SUBMITTED
    assert s.seq == 2


def test_validated():
    s = fold([submitted(), ev.validated(SID, "A1", actor="o@abi.com", seq=2, at=t(1))])
    assert s.status is Status.VALIDATED
    assert s.validated_by == "o@abi.com"
    assert s.validated_at == t(1)
    assert s.validated_seq == 2


def test_cpi_lifecycle_success():
    log = [
        submitted(),
        ev.validated(SID, "A1", actor="o@abi.com", seq=2, at=t(1)),
        ev.cpi_dispatched(SID, "A1", seq=3, idempotency_key=f"{SID}:2", attempt=1, at=t(2)),
        ev.cpi_succeeded(SID, "A1", seq=4, cpi_reference="RO-1", attempt=1, at=t(3)),
    ]
    assert fold(log[:3]).status is Status.CPI_PENDING
    s = fold(log)
    assert s.status is Status.CPI_DONE
    assert s.cpi_reference == "RO-1"


def test_cpi_transient_failure_stays_pending_then_terminal_fails():
    log = [
        submitted(),
        ev.validated(SID, "A1", actor="o@abi.com", seq=2, at=t(1)),
        ev.cpi_dispatched(SID, "A1", seq=3, idempotency_key=f"{SID}:2", attempt=1, at=t(2)),
        ev.cpi_failed(SID, "A1", seq=4, error="timeout", attempt=1, terminal=False, at=t(3)),
    ]
    s = fold(log)
    assert s.status is Status.CPI_PENDING
    assert s.cpi_error == "timeout"
    s2 = fold([*log, ev.cpi_failed(SID, "A1", seq=5, error="rejected", attempt=3, terminal=True, at=t(4))])
    assert s2.status is Status.CPI_FAILED
    assert s2.cpi_error == "rejected"


def test_credit_note_recorded_does_not_change_status():
    log = [
        submitted(),
        ev.validated(SID, "A1", actor="o@abi.com", seq=2, at=t(1)),
        ev.credit_note_recorded(SID, "A1", seq=3, credit_note_no="CN-9", outcome="issued", at=t(2)),
    ]
    s = fold(log)
    assert s.status is Status.VALIDATED
    assert s.credit_note is not None
    assert (s.credit_note.credit_note_no, s.credit_note.outcome) == ("CN-9", "issued")


def test_attachment_added():
    meta = AttachmentMeta(
        submission_id=SID,
        doc_type="delivery_note",
        seq=1,
        original_filename="a.pdf",
        storage_path="/x/a.pdf",
        sha256="a" * 64,
        size_bytes=1,
        page_count=1,
        has_text_layer=False,
        uploaded_at=t(0),
        uploaded_by="c@d.com",
    )
    s = fold([submitted(), ev.attachment_added(SID, "A1", actor="c@d.com", seq=2, meta=meta, at=t(0))])
    assert s.attachments == (meta,)


def test_fold_does_not_mutate_input():
    log = [submitted(), ev.field_overwritten(SID, "A1", actor="o@abi.com", seq=2, field="qty", prior=10, new=12, at=t(1))]
    before = [e.model_copy() for e in log]
    fold(log)
    assert log == before


def test_unsorted_input_is_sorted_by_seq():
    v = ev.validated(SID, "A1", actor="o@abi.com", seq=2, at=t(1))
    s = fold([v, submitted()])
    assert s.status is Status.VALIDATED
