from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from retpack_adapters.mock.submissions import InMemorySubmissionRepository
from retpack_core import events
from retpack_core.ids import new_id
from retpack_core.models import Status
from retpack_jobs.cpi_dispatch import SYSTEM, CpiRejectedError, CpiResult, CpiTransientError, dispatch_one, idempotency_key, pending_work, run_once
from tests.unit.conftest import CUSTOMER_A, INTERNAL, VALID_VALUES


class ScriptedCpi:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def create_return_order(self, *, idempotency_key: str, payload: Mapping[str, Any]) -> CpiResult:
        self.calls.append((idempotency_key, dict(payload)))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return CpiResult(reference=str(outcome))


def validated(repo: InMemorySubmissionRepository, at: datetime | None = None) -> str:
    sid = new_id()
    repo.append_event(CUSTOMER_A, sid, 0, events.submitted(sid, "A1", actor=CUSTOMER_A.email, values=VALID_VALUES, at=at))
    repo.append_event(INTERNAL, sid, 1, events.validated(sid, "A1", actor=INTERNAL.email, seq=2, at=at))
    return sid


def test_success_appends_dispatched_then_succeeded():
    repo = InMemorySubmissionRepository()
    sid = validated(repo)
    cpi = ScriptedCpi(["RO-1"])
    report = run_once(repo, cpi)
    assert report.succeeded == [sid]
    sub = repo.get_submission(SYSTEM, sid)
    assert sub.status is Status.CPI_DONE and sub.cpi_reference == "RO-1" and sub.cpi_attempts == 1
    assert [e.event_type.value for e in repo.get_events(SYSTEM, sid)] == ["SUBMITTED", "VALIDATED", "CPI_DISPATCHED", "CPI_SUCCEEDED"]
    key, payload = cpi.calls[0]
    assert key == f"{sid}:2" and payload["container_no"] == "1234567890" and payload["account_id"] == "A1"


def test_transient_failure_is_retried_on_next_run_with_same_key():
    repo = InMemorySubmissionRepository()
    sid = validated(repo)
    cpi = ScriptedCpi([CpiTransientError("504"), "RO-2"])
    assert run_once(repo, cpi).retried == [sid]
    mid = repo.get_submission(SYSTEM, sid)
    assert mid.status is Status.CPI_PENDING and mid.cpi_error == "504" and mid.cpi_attempts == 1
    assert run_once(repo, cpi).succeeded == [sid]
    assert cpi.calls[0][0] == cpi.calls[1][0] == f"{sid}:2"
    assert repo.get_submission(SYSTEM, sid).cpi_attempts == 2


def test_rejection_is_terminal_immediately():
    repo = InMemorySubmissionRepository()
    sid = validated(repo)
    report = run_once(repo, ScriptedCpi([CpiRejectedError("400 unknown sold-to")]))
    assert report.dead_lettered == [sid]
    sub = repo.get_submission(SYSTEM, sid)
    assert sub.status is Status.CPI_FAILED and "unknown sold-to" in (sub.cpi_error or "")


def test_transient_failures_exhaust_attempts_into_dead_letter():
    repo = InMemorySubmissionRepository()
    sid = validated(repo)
    cpi = ScriptedCpi([CpiTransientError("t1"), CpiTransientError("t2"), CpiTransientError("t3"), "never"])
    outcomes = [run_once(repo, cpi, max_attempts=3) for _ in range(4)]
    assert outcomes[0].retried == [sid] and outcomes[1].retried == [sid] and outcomes[2].dead_lettered == [sid]
    assert outcomes[3].succeeded == [] and len(cpi.calls) == 3
    assert repo.get_submission(SYSTEM, sid).status is Status.CPI_FAILED


def test_revalidated_dead_letter_gets_a_new_key():
    repo = InMemorySubmissionRepository()
    sid = validated(repo)
    run_once(repo, ScriptedCpi([CpiRejectedError("bad")]))
    sub = repo.get_submission(SYSTEM, sid)
    repo.append_event(
        INTERNAL, sid, sub.seq, events.field_overwritten(sid, "A1", actor=INTERNAL.email, seq=sub.seq + 1, field="bl_no", prior="BL-77", new="BL-78")
    )
    repo.append_event(INTERNAL, sid, sub.seq + 1, events.validated(sid, "A1", actor=INTERNAL.email, seq=sub.seq + 2))
    cpi = ScriptedCpi(["RO-9"])
    assert run_once(repo, cpi).succeeded == [sid]
    assert cpi.calls[0][0] == f"{sid}:{sub.seq + 2}" and cpi.calls[0][1]["bl_no"] == "BL-78"


def test_stale_in_flight_dispatch_is_retried_and_fresh_one_is_not():
    repo = InMemorySubmissionRepository()
    old_time = datetime.now(UTC) - timedelta(hours=2)
    stale = validated(repo, at=old_time)
    fresh = validated(repo)
    for sid, at in ((stale, old_time), (fresh, None)):
        sub = repo.get_submission(SYSTEM, sid)
        repo.append_event(SYSTEM, sid, sub.seq, events.cpi_dispatched(sid, "A1", seq=sub.seq + 1, idempotency_key=idempotency_key(sub), attempt=1, at=at))
    work = pending_work(repo, max_attempts=3, stale_after=timedelta(minutes=30))
    assert [s.submission_id for s in work] == [stale]
    cpi = ScriptedCpi(["RO-late"])
    assert run_once(repo, cpi).succeeded == [stale]
    assert cpi.calls[0][0] == f"{stale}:2"


def test_concurrent_runner_losing_the_claim_skips():
    repo = InMemorySubmissionRepository()
    sid = validated(repo)
    sub = repo.get_submission(SYSTEM, sid)
    repo.append_event(SYSTEM, sid, sub.seq, events.cpi_dispatched(sid, "A1", seq=sub.seq + 1, idempotency_key=idempotency_key(sub), attempt=1))
    cpi = ScriptedCpi(["RO-x"])
    assert dispatch_one(repo, cpi, sub) == "skipped"
    assert cpi.calls == []


def test_only_validated_or_retryable_pending_is_picked_up():
    repo = InMemorySubmissionRepository()
    sid = validated(repo)
    run_once(repo, ScriptedCpi(["RO-1"]))
    assert pending_work(repo, max_attempts=3, stale_after=timedelta(minutes=30)) == []
    other = new_id()
    repo.append_event(CUSTOMER_A, other, 0, events.submitted(other, "A1", actor=CUSTOMER_A.email, values=VALID_VALUES))
    assert pending_work(repo, max_attempts=3, stale_after=timedelta(minutes=30)) == []
    assert repo.get_submission(SYSTEM, sid).status is Status.CPI_DONE


def test_unexpected_error_leaves_submission_for_next_run():
    repo = InMemorySubmissionRepository()
    validated(repo)

    class Exploding:
        def create_return_order(self, *, idempotency_key: str, payload: Mapping[str, Any]) -> CpiResult:
            raise RuntimeError("boom")

    report = run_once(repo, Exploding())
    assert report.succeeded == [] and report.dead_lettered == []


def test_idempotency_key_requires_validation():
    repo = InMemorySubmissionRepository()
    sid = new_id()
    repo.append_event(CUSTOMER_A, sid, 0, events.submitted(sid, "A1", actor=CUSTOMER_A.email, values=VALID_VALUES))
    with pytest.raises(ValueError):
        idempotency_key(repo.get_submission(SYSTEM, sid))
