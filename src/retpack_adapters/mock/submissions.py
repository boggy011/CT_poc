"""In-memory event store with the same scoping and concurrency contract as the real backends."""

import logging
import threading

from retpack_core.errors import ConcurrencyConflictError, NotFoundError
from retpack_core.events import EventType, SubmissionEvent
from retpack_core.fold import Submission, fold
from retpack_core.models import Status
from retpack_core.principal import Principal

logger = logging.getLogger(__name__)


class InMemorySubmissionRepository:
    """Dict-backed ``SubmissionRepository``."""

    def __init__(self, seed: dict[str, list[SubmissionEvent]] | None = None) -> None:
        self._logs: dict[str, list[SubmissionEvent]] = {k: list(v) for k, v in (seed or {}).items()}
        self._lock = threading.Lock()

    def append_event(self, principal: Principal, submission_id: str, expected_seq: int, event: SubmissionEvent) -> int:
        """See ``SubmissionRepository.append_event``."""
        if event.submission_id != submission_id:
            raise ValueError("event.submission_id does not match submission_id")
        if event.seq != expected_seq + 1:
            raise ValueError(f"event.seq must be expected_seq + 1 ({expected_seq + 1}), got {event.seq}")
        with self._lock:
            log = self._logs.get(submission_id)
            if log is None:
                return self._create(principal, submission_id, expected_seq, event)
            self._require_visible(principal, log[0])
            if event.event_type is EventType.SUBMITTED:
                raise ValueError("SUBMITTED is only valid as the first event")
            if event.account_id != log[0].account_id:
                raise ValueError("event.account_id does not match the submission's account")
            if len(log) != expected_seq:
                raise ConcurrencyConflictError(f"expected seq {expected_seq}, log is at {len(log)}")
            log.append(event)
            return event.seq

    def _create(self, principal: Principal, submission_id: str, expected_seq: int, event: SubmissionEvent) -> int:
        if expected_seq != 0 or event.event_type is not EventType.SUBMITTED:
            raise NotFoundError(submission_id)
        if principal.is_scoped and event.account_id not in principal.account_ids:
            raise NotFoundError(submission_id)
        self._logs[submission_id] = [event]
        return event.seq

    def get_events(self, principal: Principal, submission_id: str) -> tuple[SubmissionEvent, ...]:
        """See ``SubmissionRepository.get_events``."""
        with self._lock:
            log = self._logs.get(submission_id)
            if log is None:
                raise NotFoundError(submission_id)
            self._require_visible(principal, log[0])
            return tuple(log)

    def get_submission(self, principal: Principal, submission_id: str) -> Submission:
        """See ``SubmissionRepository.get_submission``."""
        return fold(self.get_events(principal, submission_id))

    def list_submissions(self, principal: Principal, *, status: Status | None = None, limit: int = 200) -> tuple[Submission, ...]:
        """See ``SubmissionRepository.list_submissions``. A corrupt log is skipped and logged, never fatal."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        with self._lock:
            logs = [tuple(log) for log in self._logs.values() if self._visible(principal, log[0])]
        subs = []
        for log in logs:
            try:
                subs.append(fold(log))
            except ValueError:
                logger.exception("skipping corrupt event log for submission %s", log[0].submission_id)
        if status is not None:
            subs = [s for s in subs if s.status is status]
        subs.sort(key=lambda s: (s.submitted_at, s.submission_id), reverse=True)
        return tuple(subs[:limit])

    @staticmethod
    def _visible(principal: Principal, first: SubmissionEvent) -> bool:
        return not principal.is_scoped or first.account_id in principal.account_ids

    def _require_visible(self, principal: Principal, first: SubmissionEvent) -> None:
        if not self._visible(principal, first):
            raise NotFoundError(first.submission_id)
