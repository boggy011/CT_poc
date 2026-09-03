"""Derive current submission state from its event log.

``fold`` is pure: same events in, same ``Submission`` out. It is the single
place that knows how events change state, so the UI, the CPI job and the
contract tests all agree on what a submission "is".
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from retpack_core.events import EventType, SubmissionEvent
from retpack_core.models import AttachmentMeta, Status


class FieldOverwrite(BaseModel):
    """Audit record of one internal overwrite (NFR-05)."""

    model_config = ConfigDict(frozen=True)

    field: str
    prior: Any
    new: Any
    actor: str
    occurred_at: datetime


class CreditNote(BaseModel):
    """CN2 outcome as shown to the customer."""

    model_config = ConfigDict(frozen=True)

    credit_note_no: str
    outcome: str
    recorded_at: datetime


class Submission(BaseModel):
    """Current state of one request, folded from its events."""

    model_config = ConfigDict(frozen=True)

    submission_id: str
    account_id: str
    seq: int
    status: Status
    values: dict[str, Any]
    original_values: dict[str, Any]
    attachments: tuple[AttachmentMeta, ...]
    overwrites: tuple[FieldOverwrite, ...]
    submitted_by: str
    submitted_at: datetime
    last_event_at: datetime
    validated_by: str | None = None
    validated_at: datetime | None = None
    validated_seq: int | None = None
    cpi_reference: str | None = None
    cpi_error: str | None = None
    credit_note: CreditNote | None = None


class _State:
    """Mutable accumulator used only inside ``fold``."""

    def __init__(self, first: SubmissionEvent) -> None:
        self.data: dict[str, Any] = {
            "submission_id": first.submission_id,
            "account_id": first.account_id,
            "seq": first.seq,
            "status": Status.SUBMITTED,
            "values": dict(first.payload["values"]),
            "original_values": dict(first.payload["values"]),
            "attachments": [AttachmentMeta.model_validate(a) for a in first.payload.get("attachments", [])],
            "overwrites": [],
            "submitted_by": first.actor,
            "submitted_at": first.occurred_at,
            "last_event_at": first.occurred_at,
        }

    def apply(self, e: SubmissionEvent) -> None:
        d = self.data
        d["seq"] = e.seq
        d["last_event_at"] = e.occurred_at
        handler = _HANDLERS[e.event_type]
        handler(d, e)


def _on_attachment(d: dict[str, Any], e: SubmissionEvent) -> None:
    d["attachments"].append(AttachmentMeta.model_validate(e.payload))


def _on_overwrite(d: dict[str, Any], e: SubmissionEvent) -> None:
    p = e.payload
    if p["new"] is None:
        d["values"].pop(p["field"], None)
    else:
        d["values"][p["field"]] = p["new"]
    d["overwrites"].append(FieldOverwrite(field=p["field"], prior=p["prior"], new=p["new"], actor=e.actor, occurred_at=e.occurred_at))


def _on_validated(d: dict[str, Any], e: SubmissionEvent) -> None:
    d["status"] = Status.VALIDATED
    d["validated_by"] = e.actor
    d["validated_at"] = e.occurred_at
    d["validated_seq"] = e.seq
    d["cpi_error"] = None  # a re-validation after a dead letter re-arms dispatch


def _on_cpi_dispatched(d: dict[str, Any], e: SubmissionEvent) -> None:
    d["status"] = Status.CPI_PENDING


def _on_cpi_succeeded(d: dict[str, Any], e: SubmissionEvent) -> None:
    d["status"] = Status.CPI_DONE
    d["cpi_reference"] = e.payload["cpi_reference"]
    d["cpi_error"] = None


def _on_cpi_failed(d: dict[str, Any], e: SubmissionEvent) -> None:
    d["cpi_error"] = e.payload["error"]
    if e.payload.get("terminal"):
        d["status"] = Status.CPI_FAILED


def _on_credit_note(d: dict[str, Any], e: SubmissionEvent) -> None:
    d["credit_note"] = CreditNote(credit_note_no=e.payload["credit_note_no"], outcome=e.payload["outcome"], recorded_at=e.occurred_at)


def _on_submitted_again(d: dict[str, Any], e: SubmissionEvent) -> None:
    raise ValueError(f"SUBMITTED must be the first event only (seq {e.seq})")


_HANDLERS = {
    EventType.SUBMITTED: _on_submitted_again,
    EventType.ATTACHMENT_ADDED: _on_attachment,
    EventType.FIELD_OVERWRITTEN: _on_overwrite,
    EventType.VALIDATED: _on_validated,
    EventType.CPI_DISPATCHED: _on_cpi_dispatched,
    EventType.CPI_SUCCEEDED: _on_cpi_succeeded,
    EventType.CPI_FAILED: _on_cpi_failed,
    EventType.CREDIT_NOTE_RECORDED: _on_credit_note,
}


def fold(events: Sequence[SubmissionEvent]) -> Submission:
    """Fold an event log into the current ``Submission``.

    Args:
        events: All events of one submission, in any order.

    Returns:
        The derived current state.

    Raises:
        ValueError: If the log is empty, does not start with SUBMITTED,
            has gaps in ``seq``, or mixes submission ids.
    """
    if not events:
        raise ValueError("cannot fold an empty event log")
    ordered = sorted(events, key=lambda e: e.seq)
    first = ordered[0]
    if first.event_type is not EventType.SUBMITTED or first.seq != 1:
        raise ValueError("event log must start with SUBMITTED at seq 1")
    state = _State(first)
    for expected, e in enumerate(ordered[1:], start=2):
        if e.submission_id != first.submission_id:
            raise ValueError(f"mixed submission_id in log: {e.submission_id} != {first.submission_id}")
        if e.account_id != first.account_id:
            raise ValueError(f"mixed account_id in log at seq {e.seq}")
        if e.seq < expected:
            raise ValueError(f"duplicate event seq {e.seq}")
        if e.seq != expected:
            raise ValueError(f"gap in event seq: expected {expected}, got {e.seq}")
        state.apply(e)
    d = state.data
    d["attachments"] = tuple(d["attachments"])
    d["overwrites"] = tuple(d["overwrites"])
    return Submission(**d)
