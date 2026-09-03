"""CPI dispatch job (FR-10): validated requests become SAP return orders, never from the request thread.

Flow per submission: append ``CPI_DISPATCHED`` (claims the work; a concurrent
runner loses the append and skips), call CPI with an idempotency key derived
from the event log, append ``CPI_SUCCEEDED`` or ``CPI_FAILED``. A terminal
failure is the dead letter; the internal team corrects and re-validates, which
yields a new idempotency key.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from retpack_core import events
from retpack_core.errors import ConcurrencyConflictError, RetPackError
from retpack_core.fold import Submission
from retpack_core.models import Status
from retpack_core.ports import SubmissionRepository
from retpack_core.principal import Principal, Role

logger = logging.getLogger(__name__)

SYSTEM = Principal(email=events.SYSTEM_ACTOR, account_ids=frozenset(), role=Role.SYSTEM)
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_STALE_AFTER = timedelta(minutes=30)
"""A CPI_DISPATCHED with no result after this long is assumed lost (runner crashed mid-call) and retried."""


class CpiTransientError(RetPackError):
    """Timeout, 5xx, network: worth another attempt."""


class CpiRejectedError(RetPackError):
    """4xx or a business rejection: retrying will not help."""


@dataclass(frozen=True)
class CpiResult:
    """What CPI returns on success."""

    reference: str


class CpiClient(Protocol):
    """Existing CPI endpoint (ABI input 5)."""

    def create_return_order(self, *, idempotency_key: str, payload: Mapping[str, Any]) -> CpiResult:
        """Create the return order; must be idempotent on ``idempotency_key``.

        Raises:
            CpiTransientError: If the attempt should be retried.
            CpiRejectedError: If the request is rejected for good.
        """
        ...


@dataclass
class DispatchReport:
    """Counts for one run."""

    succeeded: list[str] = field(default_factory=list)
    retried: list[str] = field(default_factory=list)
    dead_lettered: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def idempotency_key(sub: Submission) -> str:
    """Stable per validation: ``<submission_id>:<validated_seq>``."""
    if sub.validated_seq is None:
        raise ValueError("submission has not been validated")
    return f"{sub.submission_id}:{sub.validated_seq}"


def build_payload(sub: Submission) -> dict[str, Any]:
    """PLACEHOLDER mapping until the CPI contract (input 5) arrives: all values plus identifiers."""
    return {"submission_id": sub.submission_id, "account_id": sub.account_id, "idempotency_key": idempotency_key(sub), **sub.values}


def pending_work(repo: SubmissionRepository, *, max_attempts: int, stale_after: timedelta, now: datetime | None = None) -> list[Submission]:
    """Validated requests never dispatched, transient failures with attempts left, and stale in-flight dispatches."""
    now = now or datetime.now(UTC)
    work = list(repo.list_submissions(SYSTEM, status=Status.VALIDATED, limit=1000))
    for sub in repo.list_submissions(SYSTEM, status=Status.CPI_PENDING, limit=1000):
        if sub.cpi_attempts >= max_attempts:
            continue
        failed_transiently = sub.cpi_error is not None
        stale_in_flight = sub.cpi_error is None and sub.last_event_at < now - stale_after
        if failed_transiently or stale_in_flight:
            work.append(sub)
    return work


def dispatch_one(repo: SubmissionRepository, cpi: CpiClient, sub: Submission, *, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> str:
    """Process one submission. Returns ``succeeded`` | ``retried`` | ``dead_lettered`` | ``skipped``."""
    key = idempotency_key(sub)
    attempt = sub.cpi_attempts + 1
    sid, acc, seq = sub.submission_id, sub.account_id, sub.seq
    try:
        repo.append_event(SYSTEM, sid, seq, events.cpi_dispatched(sid, acc, seq=seq + 1, idempotency_key=key, attempt=attempt))
    except ConcurrencyConflictError:
        return "skipped"
    seq += 1
    try:
        result = cpi.create_return_order(idempotency_key=key, payload=build_payload(sub))
    except CpiRejectedError as exc:
        repo.append_event(SYSTEM, sid, seq, events.cpi_failed(sid, acc, seq=seq + 1, error=str(exc), attempt=attempt, terminal=True))
        return "dead_lettered"
    except CpiTransientError as exc:
        terminal = attempt >= max_attempts
        repo.append_event(SYSTEM, sid, seq, events.cpi_failed(sid, acc, seq=seq + 1, error=str(exc), attempt=attempt, terminal=terminal))
        return "dead_lettered" if terminal else "retried"
    repo.append_event(SYSTEM, sid, seq, events.cpi_succeeded(sid, acc, seq=seq + 1, cpi_reference=result.reference, attempt=attempt))
    return "succeeded"


def run_once(
    repo: SubmissionRepository, cpi: CpiClient, *, max_attempts: int = DEFAULT_MAX_ATTEMPTS, stale_after: timedelta = DEFAULT_STALE_AFTER
) -> DispatchReport:
    """One scheduled run over all pending work."""
    report = DispatchReport()
    for sub in pending_work(repo, max_attempts=max_attempts, stale_after=stale_after):
        try:
            outcome = dispatch_one(repo, cpi, sub, max_attempts=max_attempts)
        except Exception:
            logger.exception("dispatch of %s failed unexpectedly; left for the next run", sub.submission_id)
            continue
        getattr(report, outcome).append(sub.submission_id)
        logger.info("submission %s: %s", sub.submission_id, outcome)
    return report
