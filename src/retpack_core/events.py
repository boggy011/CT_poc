"""Append-only submission event log (FR-05).

Every user or system action collapses into exactly one event. Current state
is never stored; it is folded from events (see ``retpack_core.fold``).
Factory functions below are the only sanctioned way to build events so that
payload shapes stay consistent across adapters and the AI-team contract.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from retpack_core.models import AttachmentMeta
from retpack_core.principal import Role

SYSTEM_ACTOR = "cpi-dispatch@system.local"


class EventType(StrEnum):
    """Event kinds; payload shape per kind is documented on its factory."""

    SUBMITTED = "SUBMITTED"
    ATTACHMENT_ADDED = "ATTACHMENT_ADDED"
    FIELD_OVERWRITTEN = "FIELD_OVERWRITTEN"
    VALIDATED = "VALIDATED"
    CPI_DISPATCHED = "CPI_DISPATCHED"
    CPI_SUCCEEDED = "CPI_SUCCEEDED"
    CPI_FAILED = "CPI_FAILED"
    CREDIT_NOTE_RECORDED = "CREDIT_NOTE_RECORDED"


class SubmissionEvent(BaseModel):
    """One row of the ``submission_event`` table.

    ``account_id`` is denormalised onto every event so tenant filtering and
    Unity Catalog row filters can work on the event table directly.
    """

    model_config = ConfigDict(frozen=True)

    submission_id: str
    account_id: str
    seq: int = Field(ge=1)
    event_type: EventType
    actor: str
    actor_role: Role
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def _must_be_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


def _now() -> datetime:
    return datetime.now(UTC)


def _make(
    submission_id: str,
    account_id: str,
    *,
    seq: int,
    event_type: EventType,
    actor: str,
    actor_role: Role,
    payload: dict[str, Any],
    at: datetime | None,
) -> SubmissionEvent:
    return SubmissionEvent(
        submission_id=submission_id,
        account_id=account_id,
        seq=seq,
        event_type=event_type,
        actor=actor,
        actor_role=actor_role,
        occurred_at=at or _now(),
        payload=payload,
    )


def submitted(
    submission_id: str,
    account_id: str,
    *,
    actor: str,
    values: dict[str, Any],
    attachments: Sequence[AttachmentMeta] = (),
    seq: int = 1,
    at: datetime | None = None,
) -> SubmissionEvent:
    """Customer submitted a new request.

    Payload: ``{"values": {...}, "attachments": [AttachmentMeta...]}``. Attachments
    uploaded with the form ride on this event so a submit is exactly one append.
    """
    payload = {"values": dict(values), "attachments": [m.model_dump(mode="json") for m in attachments]}
    return _make(submission_id, account_id, seq=seq, event_type=EventType.SUBMITTED, actor=actor, actor_role=Role.CUSTOMER, payload=payload, at=at)


def attachment_added(submission_id: str, account_id: str, *, actor: str, seq: int, meta: AttachmentMeta, at: datetime | None = None) -> SubmissionEvent:
    """A PDF was stored and linked. Payload: ``AttachmentMeta`` as JSON-safe dict."""
    return _make(
        submission_id,
        account_id,
        seq=seq,
        event_type=EventType.ATTACHMENT_ADDED,
        actor=actor,
        actor_role=Role.CUSTOMER,
        payload=meta.model_dump(mode="json"),
        at=at,
    )


def field_overwritten(
    submission_id: str, account_id: str, *, actor: str, seq: int, field: str, prior: Any, new: Any, at: datetime | None = None
) -> SubmissionEvent:
    """Internal user overwrote one field (FR-09). Payload: ``{"field", "prior", "new"}``."""
    return _make(
        submission_id,
        account_id,
        seq=seq,
        event_type=EventType.FIELD_OVERWRITTEN,
        actor=actor,
        actor_role=Role.INTERNAL,
        payload={"field": field, "prior": prior, "new": new},
        at=at,
    )


def validated(submission_id: str, account_id: str, *, actor: str, seq: int, at: datetime | None = None) -> SubmissionEvent:
    """Internal user released the request downstream. Payload: empty."""
    return _make(submission_id, account_id, seq=seq, event_type=EventType.VALIDATED, actor=actor, actor_role=Role.INTERNAL, payload={}, at=at)


def cpi_dispatched(submission_id: str, account_id: str, *, seq: int, idempotency_key: str, attempt: int, at: datetime | None = None) -> SubmissionEvent:
    """CPI job started an attempt. Payload: ``{"idempotency_key", "attempt"}``."""
    return _make(
        submission_id,
        account_id,
        seq=seq,
        event_type=EventType.CPI_DISPATCHED,
        actor=SYSTEM_ACTOR,
        actor_role=Role.SYSTEM,
        payload={"idempotency_key": idempotency_key, "attempt": attempt},
        at=at,
    )


def cpi_succeeded(submission_id: str, account_id: str, *, seq: int, cpi_reference: str, attempt: int, at: datetime | None = None) -> SubmissionEvent:
    """CPI accepted the return order. Payload: ``{"cpi_reference", "attempt"}``."""
    return _make(
        submission_id,
        account_id,
        seq=seq,
        event_type=EventType.CPI_SUCCEEDED,
        actor=SYSTEM_ACTOR,
        actor_role=Role.SYSTEM,
        payload={"cpi_reference": cpi_reference, "attempt": attempt},
        at=at,
    )


def cpi_failed(submission_id: str, account_id: str, *, seq: int, error: str, attempt: int, terminal: bool, at: datetime | None = None) -> SubmissionEvent:
    """A CPI attempt failed. ``terminal=True`` is the dead letter. Payload: ``{"error", "attempt", "terminal"}``."""
    return _make(
        submission_id,
        account_id,
        seq=seq,
        event_type=EventType.CPI_FAILED,
        actor=SYSTEM_ACTOR,
        actor_role=Role.SYSTEM,
        payload={"error": error, "attempt": attempt, "terminal": terminal},
        at=at,
    )


def credit_note_recorded(submission_id: str, account_id: str, *, seq: int, credit_note_no: str, outcome: str, at: datetime | None = None) -> SubmissionEvent:
    """CN2 outcome landed. Payload: ``{"credit_note_no", "outcome"}``."""
    return _make(
        submission_id,
        account_id,
        seq=seq,
        event_type=EventType.CREDIT_NOTE_RECORDED,
        actor=SYSTEM_ACTOR,
        actor_role=Role.SYSTEM,
        payload={"credit_note_no": credit_note_no, "outcome": outcome},
        at=at,
    )
