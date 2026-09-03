"""Transactional store for the submission event log (swappable: mock | delta | lakebase)."""

from typing import Protocol

from retpack_core.events import SubmissionEvent
from retpack_core.fold import Submission
from retpack_core.models import Status
from retpack_core.principal import Principal


class SubmissionRepository(Protocol):
    """Append-only event store with principal-scoped reads.

    Scoped principals (customers) only ever see submissions whose
    ``account_id`` is in ``principal.account_ids``; anything else raises
    ``NotFoundError``. Unscoped principals (internal, system) see all.
    """

    def append_event(self, principal: Principal, submission_id: str, expected_seq: int, event: SubmissionEvent) -> int:
        """Append one event.

        Args:
            principal: Caller; must be allowed to see ``submission_id``.
            submission_id: Target submission. For a new submission
                ``expected_seq`` is 0 and ``event`` is SUBMITTED.
            expected_seq: The last ``seq`` the caller observed.
            event: Event to append; ``event.seq`` must equal ``expected_seq + 1``.

        Returns:
            The new sequence number.

        Raises:
            ConcurrencyConflictError: If another writer appended first.
            NotFoundError: If the submission is outside the principal's scope.
            ValueError: If ``event.seq`` is not ``expected_seq + 1``.
        """
        ...

    def get_events(self, principal: Principal, submission_id: str) -> tuple[SubmissionEvent, ...]:
        """All events of one submission ordered by ``seq``.

        Raises:
            NotFoundError: If unknown or outside the principal's scope.
        """
        ...

    def get_submission(self, principal: Principal, submission_id: str) -> Submission:
        """Folded current state of one submission.

        Raises:
            NotFoundError: If unknown or outside the principal's scope.
        """
        ...

    def list_submissions(self, principal: Principal, *, status: Status | None = None, limit: int = 200) -> tuple[Submission, ...]:
        """Submissions visible to the principal, newest first, optionally filtered by status."""
        ...
