from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from retpack_core import events as ev
from retpack_core.events import EventType, SubmissionEvent
from retpack_core.principal import Role

SID = "0190f0a0-0000-7000-8000-000000000001"
AT = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)


def test_event_requires_tz_aware_timestamp():
    with pytest.raises(ValidationError, match="timezone"):
        SubmissionEvent(
            submission_id=SID,
            account_id="A1",
            seq=1,
            event_type=EventType.SUBMITTED,
            actor="c@d.com",
            actor_role=Role.CUSTOMER,
            occurred_at=datetime(2026, 9, 3),
            payload={},
        )


def test_event_seq_starts_at_one():
    with pytest.raises(ValidationError):
        ev.submitted(SID, "A1", actor="c@d.com", values={"x": "1"}, seq=0, at=AT)


def test_event_is_frozen():
    e = ev.submitted(SID, "A1", actor="c@d.com", values={"x": "1"}, seq=1, at=AT)
    with pytest.raises(ValidationError):
        e.seq = 2  # type: ignore[misc]


def test_submitted_factory():
    e = ev.submitted(SID, "A1", actor="c@d.com", values={"x": "1"}, seq=1, at=AT)
    assert e.event_type is EventType.SUBMITTED
    assert e.actor_role is Role.CUSTOMER
    assert e.payload == {"values": {"x": "1"}, "attachments": []}
    assert e.occurred_at == AT


def test_factories_default_timestamp_is_utc_now():
    e = ev.validated(SID, "A1", actor="ops@abi.com", seq=2)
    assert e.occurred_at.tzinfo is not None
    assert abs((datetime.now(UTC) - e.occurred_at).total_seconds()) < 5


def test_field_overwritten_factory_carries_prior_and_new():
    e = ev.field_overwritten(SID, "A1", actor="ops@abi.com", seq=2, field="qty", prior=1, new=2, at=AT)
    assert e.event_type is EventType.FIELD_OVERWRITTEN
    assert e.actor_role is Role.INTERNAL
    assert e.payload == {"field": "qty", "prior": 1, "new": 2}


def test_cpi_factories():
    d = ev.cpi_dispatched(SID, "A1", seq=3, idempotency_key=f"{SID}:2", attempt=1, at=AT)
    s = ev.cpi_succeeded(SID, "A1", seq=4, cpi_reference="RO-1", attempt=1, at=AT)
    f = ev.cpi_failed(SID, "A1", seq=4, error="timeout", attempt=3, terminal=True, at=AT)
    assert d.actor_role is Role.SYSTEM and d.payload["idempotency_key"] == f"{SID}:2"
    assert s.payload == {"cpi_reference": "RO-1", "attempt": 1}
    assert f.payload == {"error": "timeout", "attempt": 3, "terminal": True}


def test_credit_note_factory():
    e = ev.credit_note_recorded(SID, "A1", seq=5, credit_note_no="CN-9", outcome="issued", at=AT)
    assert e.event_type is EventType.CREDIT_NOTE_RECORDED
    assert e.payload == {"credit_note_no": "CN-9", "outcome": "issued"}


def test_attachment_added_factory_embeds_meta():
    from retpack_core.models import AttachmentMeta

    meta = AttachmentMeta(
        submission_id=SID,
        account_id="A1",
        doc_type="delivery_note",
        seq=1,
        original_filename="a.pdf",
        storage_path="/x/a.pdf",
        sha256="a" * 64,
        size_bytes=1,
        page_count=1,
        has_text_layer=False,
        uploaded_at=AT,
        uploaded_by="c@d.com",
    )
    e = ev.attachment_added(SID, "A1", actor="c@d.com", seq=2, meta=meta, at=AT)
    assert e.payload["sha256"] == "a" * 64
    assert datetime.fromisoformat(e.payload["uploaded_at"]) == AT


def test_event_round_trips_through_json():
    e = ev.submitted(SID, "A1", actor="c@d.com", values={"x": "1", "n": 2}, seq=1, at=AT)
    again = SubmissionEvent.model_validate_json(e.model_dump_json())
    assert again == e
