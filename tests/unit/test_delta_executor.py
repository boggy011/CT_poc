from typing import Any

import pytest

from retpack_adapters.delta.executor import DeltaExecutor, is_concurrent_error
from retpack_adapters.sql.executor import delta_dialect


class FakeRow:
    def __init__(self, **fields: Any) -> None:
        self._f = fields

    def asDict(self) -> dict[str, Any]:  # noqa: N802 - mirrors the connector's Row API
        return dict(self._f)


class FakeCursor:
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn
        self.rowcount = -1
        self._rows: list[Any] = []

    def execute(self, sql: str, params: Any = None) -> None:
        self.conn.calls.append((sql, params))
        outcome = self.conn.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        self._rows = list(outcome)

    def fetchall(self) -> list[Any]:
        return self._rows

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def close(self) -> None:
        self.conn.closed += 1


class FakeConnection:
    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.calls: list[tuple[str, Any]] = []
        self.closed = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def test_merge_reports_inserted_rows():
    conn = FakeConnection([[FakeRow(num_affected_rows=1, num_updated_rows=0, num_deleted_rows=0, num_inserted_rows=1)]])
    ex = DeltaExecutor(lambda: conn)
    assert ex.execute(delta_dialect("c", "s").insert_event_sql, ["x"] * 9) == 1
    assert conn.calls[0][1] == ["x"] * 9
    assert conn.closed == 1


def test_merge_lost_race_reports_zero():
    conn = FakeConnection([[FakeRow(num_affected_rows=0, num_updated_rows=0, num_deleted_rows=0, num_inserted_rows=0)]])
    assert DeltaExecutor(lambda: conn).execute("MERGE INTO t ...", []) == 0


def test_concurrent_error_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("retpack_adapters.delta.executor.time.sleep", lambda s: None)
    err = RuntimeError("[DELTA_CONCURRENT_APPEND] ConcurrentAppendException: Files were added")
    conn = FakeConnection([err, [FakeRow(num_inserted_rows=1)]])
    assert DeltaExecutor(lambda: conn).execute("MERGE INTO t", []) == 1
    assert len(conn.calls) == 2


def test_concurrent_error_gives_up_after_max_attempts(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("retpack_adapters.delta.executor.time.sleep", lambda s: None)
    err = RuntimeError("ConcurrentAppendException")
    conn = FakeConnection([err, err, err])
    with pytest.raises(RuntimeError):
        DeltaExecutor(lambda: conn).execute("MERGE INTO t", [])
    assert len(conn.calls) == 3


def test_other_errors_are_not_retried():
    conn = FakeConnection([RuntimeError("TABLE_OR_VIEW_NOT_FOUND")])
    with pytest.raises(RuntimeError):
        DeltaExecutor(lambda: conn).execute("MERGE INTO t", [])
    assert len(conn.calls) == 1


def test_query_returns_tuples():
    conn = FakeConnection([[("a", 1), ("b", 2)]])
    assert DeltaExecutor(lambda: conn).query("SELECT 1") == [("a", 1), ("b", 2)]


def test_is_concurrent_error_markers():
    assert is_concurrent_error(Exception("DELTA_CONCURRENT_WRITE"))
    assert not is_concurrent_error(Exception("syntax error"))


def test_stale_session_reconnects_once_and_retries():
    err = RuntimeError("RequestError: Error during request to server: INVALID_STATE: Invalid SessionHandle: SessionHandle [abc]")
    first = FakeConnection([err])
    second = FakeConnection([[("ok",)]])
    conns = iter([first, second])
    ex = DeltaExecutor(lambda: next(conns))
    assert ex.query("SELECT 1") == [("ok",)]
    assert len(first.calls) == 1 and len(second.calls) == 1


def test_stale_session_on_execute_reconnects():
    err = RuntimeError("Invalid SessionHandle")
    first = FakeConnection([err])
    second = FakeConnection([[FakeRow(num_inserted_rows=1)]])
    conns = iter([first, second])
    assert DeltaExecutor(lambda: next(conns)).execute("MERGE INTO t", []) == 1


def test_session_error_twice_propagates():
    err = RuntimeError("Invalid SessionHandle")
    conns = iter([FakeConnection([err]), FakeConnection([err])])
    with pytest.raises(RuntimeError):
        DeltaExecutor(lambda: next(conns)).query("SELECT 1")


def test_non_session_error_does_not_reconnect():
    conns_used = []

    def connect():
        conn = FakeConnection([RuntimeError("TABLE_OR_VIEW_NOT_FOUND")])
        conns_used.append(conn)
        return conn

    with pytest.raises(RuntimeError):
        DeltaExecutor(connect).query("SELECT 1")
    assert len(conns_used) == 1
