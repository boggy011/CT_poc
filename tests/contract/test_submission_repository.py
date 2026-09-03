"""Behavioural contract every SubmissionRepository must satisfy. Parametrized over backends."""

import threading
from datetime import UTC, datetime, timedelta

import pytest

from retpack_core import events
from retpack_core.errors import ConcurrencyConflictError, NotFoundError
from retpack_core.events import EventType
from retpack_core.ids import new_id
from retpack_core.models import Status
from retpack_core.ports import SubmissionRepository
from retpack_core.principal import Principal
from tests.conftest import CUSTOMER_A, INTERNAL

VALUES = {
    "account_id": "A1",
    "sku_code": "KEG50",
    "container_no": "1234567890",
    "bl_no": "BL-1",
    "destination": "Antwerp",
    "quantity": 1,
    "pickup_date": "2026-09-10",
}


def create(repo: SubmissionRepository, principal: Principal = CUSTOMER_A, account: str = "A1", at: datetime | None = None) -> str:
    sid = new_id()
    repo.append_event(principal, sid, 0, events.submitted(sid, account, actor=principal.email, values={**VALUES, "account_id": account}, at=at))
    return sid


def test_append_and_read_round_trip(repo: SubmissionRepository):
    sid = new_id()
    ev = events.submitted(sid, "A1", actor=CUSTOMER_A.email, values=VALUES)
    assert repo.append_event(CUSTOMER_A, sid, 0, ev) == 1
    got = repo.get_events(CUSTOMER_A, sid)
    assert got == (ev,)


def test_events_come_back_in_seq_order(repo: SubmissionRepository):
    sid = create(repo)
    repo.append_event(INTERNAL, sid, 1, events.field_overwritten(sid, "A1", actor=INTERNAL.email, seq=2, field="quantity", prior=1, new=2))
    repo.append_event(INTERNAL, sid, 2, events.validated(sid, "A1", actor=INTERNAL.email, seq=3))
    assert [e.seq for e in repo.get_events(INTERNAL, sid)] == [1, 2, 3]
    assert [e.event_type for e in repo.get_events(INTERNAL, sid)][-1] is EventType.VALIDATED


def test_append_returns_new_seq(repo: SubmissionRepository):
    sid = create(repo)
    assert repo.append_event(INTERNAL, sid, 1, events.validated(sid, "A1", actor=INTERNAL.email, seq=2)) == 2


def test_stale_expected_seq_conflicts(repo: SubmissionRepository):
    sid = create(repo)
    repo.append_event(INTERNAL, sid, 1, events.validated(sid, "A1", actor=INTERNAL.email, seq=2))
    with pytest.raises(ConcurrencyConflictError):
        repo.append_event(INTERNAL, sid, 1, events.validated(sid, "A1", actor=INTERNAL.email, seq=2))
    assert len(repo.get_events(INTERNAL, sid)) == 2


def test_event_seq_must_follow_expected(repo: SubmissionRepository):
    sid = create(repo)
    with pytest.raises(ValueError):
        repo.append_event(INTERNAL, sid, 1, events.validated(sid, "A1", actor=INTERNAL.email, seq=5))


def test_event_submission_id_must_match(repo: SubmissionRepository):
    sid = create(repo)
    with pytest.raises(ValueError):
        repo.append_event(INTERNAL, sid, 1, events.validated(new_id(), "A1", actor=INTERNAL.email, seq=2))


def test_append_to_unknown_submission_is_not_found(repo: SubmissionRepository):
    sid = new_id()
    with pytest.raises(NotFoundError):
        repo.append_event(INTERNAL, sid, 1, events.validated(sid, "A1", actor=INTERNAL.email, seq=2))


def test_create_requires_submitted_at_seq_zero(repo: SubmissionRepository):
    sid = new_id()
    with pytest.raises((NotFoundError, ValueError)):
        repo.append_event(INTERNAL, sid, 0, events.validated(sid, "A1", actor=INTERNAL.email, seq=1))


def test_get_unknown_is_not_found(repo: SubmissionRepository):
    with pytest.raises(NotFoundError):
        repo.get_events(INTERNAL, new_id())
    with pytest.raises(NotFoundError):
        repo.get_submission(INTERNAL, new_id())


def test_get_submission_folds(repo: SubmissionRepository):
    sid = create(repo)
    repo.append_event(INTERNAL, sid, 1, events.validated(sid, "A1", actor=INTERNAL.email, seq=2))
    sub = repo.get_submission(INTERNAL, sid)
    assert sub.status is Status.VALIDATED and sub.seq == 2 and sub.values["container_no"] == "1234567890"


def test_list_newest_first_with_status_filter_and_limit(repo: SubmissionRepository):
    t0 = datetime(2026, 9, 1, tzinfo=UTC)
    older = create(repo, at=t0)
    newer = create(repo, at=t0 + timedelta(hours=1))
    newest = create(repo, at=t0 + timedelta(hours=2))
    repo.append_event(INTERNAL, older, 1, events.validated(older, "A1", actor=INTERNAL.email, seq=2))
    ids = [s.submission_id for s in repo.list_submissions(CUSTOMER_A)]
    assert ids[:3] == [newest, newer, older]
    assert [s.submission_id for s in repo.list_submissions(CUSTOMER_A, status=Status.VALIDATED)] == [older]
    assert [s.submission_id for s in repo.list_submissions(CUSTOMER_A, limit=1)] == [newest]


def test_list_empty_when_nothing_visible(repo: SubmissionRepository):
    assert repo.list_submissions(CUSTOMER_A) == ()


def test_concurrent_appends_exactly_one_wins(repo: SubmissionRepository):
    sid = create(repo)
    outcomes: list[str] = []
    barrier = threading.Barrier(4)

    def worker(n: int) -> None:
        barrier.wait()
        try:
            repo.append_event(INTERNAL, sid, 1, events.field_overwritten(sid, "A1", actor=INTERNAL.email, seq=2, field="quantity", prior=1, new=n))
            outcomes.append("ok")
        except ConcurrencyConflictError:
            outcomes.append("conflict")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["conflict", "conflict", "conflict", "ok"]
    assert len(repo.get_events(INTERNAL, sid)) == 2
