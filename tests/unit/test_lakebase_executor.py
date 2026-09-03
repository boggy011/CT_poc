from typing import Any

import pytest

from retpack_adapters.lakebase.executor import LakebaseExecutor, translate_placeholders


class BrokenError(Exception):
    pass


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
        if isinstance(outcome, int):
            self.rowcount = outcome
        else:
            self._rows = list(outcome)

    def fetchall(self) -> list[Any]:
        return self._rows

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        pass


class FakeConnection:
    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.calls: list[tuple[str, Any]] = []
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def close(self) -> None:
        self.closed = True


def test_placeholders_translated():
    assert translate_placeholders("SELECT ? , ?") == "SELECT %s , %s"


def test_execute_returns_rowcount_and_translates():
    conn = FakeConnection([1])
    ex = LakebaseExecutor(lambda: conn, operational_error=BrokenError)
    assert ex.execute("INSERT INTO t VALUES (?, ?) ON CONFLICT DO NOTHING", ["a", 1]) == 1
    assert conn.calls == [("INSERT INTO t VALUES (%s, %s) ON CONFLICT DO NOTHING", ["a", 1])]


def test_conflict_reports_zero():
    conn = FakeConnection([0])
    assert LakebaseExecutor(lambda: conn, operational_error=BrokenError).execute("INSERT ...", []) == 0


def test_reconnects_once_on_operational_error():
    first = FakeConnection([BrokenError("token expired")])
    second = FakeConnection([[("x",)]])
    conns = iter([first, second])
    ex = LakebaseExecutor(lambda: next(conns), operational_error=BrokenError)
    assert ex.query("SELECT ?", [1]) == [("x",)]
    assert first.closed is True


def test_second_operational_error_propagates():
    conns = iter([FakeConnection([BrokenError("a")]), FakeConnection([BrokenError("b")])])
    with pytest.raises(BrokenError):
        LakebaseExecutor(lambda: next(conns), operational_error=BrokenError).query("SELECT 1")
