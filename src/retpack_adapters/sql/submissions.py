"""``SubmissionRepository`` over any SQL engine with a ``Dialect``."""

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from retpack_adapters.sql.executor import EVENT_COLUMNS, Dialect, SqlExecutor
from retpack_core.errors import ConcurrencyConflictError, NotFoundError
from retpack_core.events import EventType, SubmissionEvent
from retpack_core.fold import Submission, fold
from retpack_core.models import Status
from retpack_core.principal import Principal, Role

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 5_000
"""Upper bound on submissions folded for one filtered listing (status filters are applied after folding)."""


class SqlSubmissionRepository:
    """Scoping happens in the SQL (``account_id IN (...)``), never by filtering rows in Python."""

    def __init__(self, executor: SqlExecutor, dialect: Dialect) -> None:
        self._db = executor
        self._d = dialect
        self._cols = ", ".join(c for c in EVENT_COLUMNS if c != "ingested_at")

    # -- writes -----------------------------------------------------------------

    def append_event(self, principal: Principal, submission_id: str, expected_seq: int, event: SubmissionEvent) -> int:
        """See ``SubmissionRepository.append_event``."""
        if event.submission_id != submission_id:
            raise ValueError("event.submission_id does not match submission_id")
        if event.seq != expected_seq + 1:
            raise ValueError(f"event.seq must be expected_seq + 1 ({expected_seq + 1}), got {event.seq}")
        if expected_seq == 0:
            self._check_create(principal, event)
        else:
            self._check_append(principal, submission_id, expected_seq, event)
        inserted = self._db.execute(self._d.insert_event_sql, self._row(event))
        if inserted == 0:
            raise ConcurrencyConflictError(f"expected seq {expected_seq}, another event was appended first")
        return event.seq

    def _check_create(self, principal: Principal, event: SubmissionEvent) -> None:
        if event.event_type is not EventType.SUBMITTED:
            raise NotFoundError(event.submission_id)
        if principal.is_scoped and event.account_id not in principal.account_ids:
            raise NotFoundError(event.submission_id)

    def _check_append(self, principal: Principal, submission_id: str, expected_seq: int, event: SubmissionEvent) -> None:
        rows = self._db.query(f"SELECT MIN(account_id), MAX(seq) FROM {self._d.event_table} WHERE submission_id = ?", [submission_id])
        account, max_seq = rows[0] if rows else (None, None)
        if account is None or (principal.is_scoped and account not in principal.account_ids):
            raise NotFoundError(submission_id)
        if event.event_type is EventType.SUBMITTED:
            raise ValueError("SUBMITTED is only valid as the first event")
        if event.account_id != account:
            raise ValueError("event.account_id does not match the submission's account")
        if int(max_seq) != expected_seq:
            raise ConcurrencyConflictError(f"expected seq {expected_seq}, log is at {max_seq}")

    def _row(self, e: SubmissionEvent) -> list[Any]:
        now = datetime.now(UTC)
        return [
            e.submission_id,
            e.account_id,
            e.seq,
            e.event_type.value,
            e.actor,
            e.actor_role.value,
            self._ts(e.occurred_at),
            json.dumps(e.payload, separators=(",", ":")),
            self._ts(now),
        ]

    def _ts(self, value: datetime) -> Any:
        utc = value.astimezone(UTC)
        return utc.isoformat() if self._d.timestamps_as_text else utc

    # -- reads ------------------------------------------------------------------

    def get_events(self, principal: Principal, submission_id: str) -> tuple[SubmissionEvent, ...]:
        """See ``SubmissionRepository.get_events``."""
        scope_sql, scope_params = self._scope(principal)
        if scope_sql is None:
            raise NotFoundError(submission_id)
        rows = self._db.query(f"SELECT {self._cols} FROM {self._d.event_table} WHERE submission_id = ?{scope_sql} ORDER BY seq", [submission_id, *scope_params])
        if not rows:
            raise NotFoundError(submission_id)
        return tuple(self._decode(r) for r in rows)

    def get_submission(self, principal: Principal, submission_id: str) -> Submission:
        """See ``SubmissionRepository.get_submission``."""
        return fold(self.get_events(principal, submission_id))

    def list_submissions(self, principal: Principal, *, status: Status | None = None, limit: int = 200) -> tuple[Submission, ...]:
        """See ``SubmissionRepository.list_submissions``."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        scope_sql, scope_params = self._scope(principal)
        if scope_sql is None:
            return ()
        candidates = limit if status is None else min(limit * 10, MAX_CANDIDATES)
        t = self._d.event_table
        sql = (
            f"SELECT {', '.join('e.' + c for c in EVENT_COLUMNS if c != 'ingested_at')} FROM {t} e "
            f"JOIN (SELECT submission_id FROM {t} WHERE seq = 1{scope_sql} ORDER BY occurred_at DESC, submission_id DESC LIMIT {int(candidates)}) h "
            "ON h.submission_id = e.submission_id ORDER BY e.submission_id, e.seq"
        )
        logs: dict[str, list[SubmissionEvent]] = {}
        for row in self._db.query(sql, scope_params):
            e = self._decode(row)
            logs.setdefault(e.submission_id, []).append(e)
        subs = []
        for sid, log in logs.items():
            try:
                subs.append(fold(log))
            except ValueError:
                logger.exception("skipping corrupt event log for submission %s", sid)
        if status is not None:
            subs = [s for s in subs if s.status is status]
        subs.sort(key=lambda s: (s.submitted_at, s.submission_id), reverse=True)
        return tuple(subs[:limit])

    def _scope(self, principal: Principal) -> tuple[str | None, list[str]]:
        """SQL fragment restricting rows to the principal's accounts. None means nothing is visible."""
        if not principal.is_scoped:
            return "", []
        accounts = sorted(principal.account_ids)
        if not accounts:
            return None, []
        return f" AND account_id IN ({', '.join('?' for _ in accounts)})", accounts

    def _decode(self, row: Sequence[Any]) -> SubmissionEvent:
        submission_id, account_id, seq, event_type, actor, actor_role, occurred_at, payload = row
        return SubmissionEvent(
            submission_id=str(submission_id),
            account_id=str(account_id),
            seq=int(seq),
            event_type=EventType(str(event_type)),
            actor=str(actor),
            actor_role=Role(str(actor_role)),
            occurred_at=_to_datetime(occurred_at),
            payload=payload if isinstance(payload, dict) else json.loads(payload),
        )


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value))
