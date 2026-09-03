"""Internal review: overwrite fields and validate (FR-09), each as one event append."""

import logging
from typing import Any

from retpack_core import events
from retpack_core.errors import ConcurrencyConflictError, NotPermittedError, StateError, ValidationFailedError
from retpack_core.events import SubmissionEvent
from retpack_core.fieldspec import FormSpec, validate_field, validate_values
from retpack_core.fold import Submission, fold
from retpack_core.models import Status
from retpack_core.ports import Ports
from retpack_core.principal import Principal
from retpack_core.services.options import Choice, enum_choices, enum_options

logger = logging.getLogger(__name__)

REVIEWABLE = frozenset({Status.SUBMITTED, Status.CPI_FAILED})
"""Statuses the internal team may act on. A dead letter (CPI_FAILED) is corrected and re-validated here."""


class ReviewService:
    """Actions of the 3-person internal team."""

    def __init__(self, ports: Ports, spec: FormSpec) -> None:
        self._ports = ports
        self._spec = spec

    def enum_choices(self, principal: Principal, *, account_id: str) -> dict[str, tuple[Choice, ...]]:
        """Labelled dropdown options for the correction widgets."""
        return enum_choices(self._ports.reference, self._spec, principal, account_id=account_id)

    def correctable_fields(self) -> tuple[str, ...]:
        """Field names the internal team may overwrite (everything except the owning account)."""
        account = self._spec.account_field
        return tuple(f.name for f in self._spec.fields if account is None or f.name != account.name)

    def overwrite_field(self, principal: Principal, submission_id: str, *, field: str, new_value: Any, expected_seq: int) -> Submission:
        """Replace one customer-entered value, keeping the prior value in the event.

        Raises:
            NotPermittedError: If the principal is not internal.
            NotFoundError: If the submission is unknown.
            ConcurrencyConflictError: If ``expected_seq`` is stale.
            StateError: If the submission is not in a reviewable status.
            ValidationFailedError: If the field is unknown, is the owning account,
                or the value breaks its format rule.
        """
        log, sub = self._load(principal, submission_id, expected_seq)
        if field not in self.correctable_fields():
            raise ValidationFailedError({field: ["unknown field" if field not in {f.name for f in self._spec.fields} else "cannot be changed"]})
        f = self._spec.field(field)
        options = enum_options(self._ports.reference, self._spec, principal, account_id=sub.account_id)
        value, messages = validate_field(f, new_value, options=options.get(field, ()))
        if messages:
            raise ValidationFailedError({field: messages})
        event = events.field_overwritten(
            sub.submission_id, sub.account_id, actor=principal.email, seq=expected_seq + 1, field=field, prior=sub.values.get(field), new=value
        )
        logger.info("submission %s field %s overwritten by %s", sub.submission_id, field, principal.email)
        return self._append(principal, log, expected_seq, event)

    def validate(self, principal: Principal, submission_id: str, *, expected_seq: int) -> Submission:
        """Release the request downstream. Mandatory-field rules must hold on current values.

        Raises:
            NotPermittedError: If the principal is not internal.
            NotFoundError: If the submission is unknown.
            ConcurrencyConflictError: If ``expected_seq`` is stale.
            StateError: If not in a reviewable status.
            ValidationFailedError: If current values violate the spec.
        """
        log, sub = self._load(principal, submission_id, expected_seq)
        options = enum_options(self._ports.reference, self._spec, principal, account_id=sub.account_id)
        result = validate_values(sub.values, self._spec, enum_options=options)
        if not result.ok:
            raise ValidationFailedError(result.errors)
        event = events.validated(sub.submission_id, sub.account_id, actor=principal.email, seq=expected_seq + 1)
        logger.info("submission %s validated by %s", sub.submission_id, principal.email)
        return self._append(principal, log, expected_seq, event)

    def _load(self, principal: Principal, submission_id: str, expected_seq: int) -> tuple[tuple[SubmissionEvent, ...], Submission]:
        if not principal.is_internal:
            raise NotPermittedError("only the internal team can review requests")
        log = self._ports.submissions.get_events(principal, submission_id)
        sub = fold(log)
        if sub.seq != expected_seq:
            raise ConcurrencyConflictError(f"submission changed: expected seq {expected_seq}, now {sub.seq}")
        if sub.status not in REVIEWABLE:
            raise StateError(f"request is {sub.status}; only {', '.join(sorted(s.value for s in REVIEWABLE))} requests can be reviewed")
        return log, sub

    def _append(self, principal: Principal, log: tuple[SubmissionEvent, ...], expected_seq: int, event: SubmissionEvent) -> Submission:
        self._ports.submissions.append_event(principal, event.submission_id, expected_seq, event)
        return fold([*log, event])
