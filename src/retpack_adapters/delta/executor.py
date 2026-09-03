"""``SqlExecutor`` over ``databricks-sql-connector``.

MERGE statements return a single result row with ``num_inserted_rows``; that
is what ``execute`` reports so the shared repository can detect a lost race.
Delta's optimistic concurrency surfaces as a ``ServerOperationError`` whose
message names a concurrent-modification exception; those are retried a few
times with backoff before giving up.
"""

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol

logger = logging.getLogger(__name__)

CONCURRENT_MARKERS = ("CONCURRENT_APPEND", "CONCURRENTAPPEND", "CONCURRENT_TRANSACTION", "CONCURRENT_WRITE", "CONCURRENTWRITE", "DELTA_CONCURRENT")
MAX_ATTEMPTS = 3
BACKOFF_S = 0.2


class _Cursor(Protocol):
    def execute(self, sql: str, params: Any = None) -> Any: ...
    def fetchall(self) -> list[Any]: ...
    def fetchone(self) -> Any: ...
    def close(self) -> None: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...


class DeltaExecutor:
    """One connection per executor; the factory supplies the connection lazily."""

    def __init__(self, connect: Callable[[], _Connection]) -> None:
        self._connect = connect
        self._conn: _Connection | None = None

    def _cursor(self) -> _Cursor:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn.cursor()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        """See ``SqlExecutor.query``."""
        cursor = self._cursor()
        try:
            cursor.execute(sql, list(params))
            return [tuple(r) for r in cursor.fetchall()]
        finally:
            cursor.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """See ``SqlExecutor.execute``; retries concurrent-modification failures."""
        attempt = 0
        while True:
            attempt += 1
            try:
                return self._execute_once(sql, params)
            except Exception as exc:
                if not is_concurrent_error(exc) or attempt >= MAX_ATTEMPTS:
                    raise
                logger.warning("Delta concurrent modification (attempt %d/%d): %s", attempt, MAX_ATTEMPTS, exc)
                time.sleep(BACKOFF_S * 2 ** (attempt - 1))

    def _execute_once(self, sql: str, params: Sequence[Any]) -> int:
        cursor = self._cursor()
        try:
            cursor.execute(sql, list(params))
            if sql.lstrip()[:5].upper() == "MERGE":
                row = cursor.fetchone()
                return int(_field(row, "num_inserted_rows", 3)) if row is not None else 0
            rowcount = getattr(cursor, "rowcount", -1)
            return int(rowcount) if rowcount is not None and rowcount >= 0 else 0
        finally:
            cursor.close()


def is_concurrent_error(exc: BaseException) -> bool:
    """True if a connector error describes a Delta concurrent-modification conflict."""
    text = str(exc).upper().replace(" ", "")
    return any(marker in text for marker in CONCURRENT_MARKERS)


def _field(row: Any, name: str, index: int) -> Any:
    if hasattr(row, "asDict"):
        return row.asDict()[name]
    if isinstance(row, dict):
        return row[name]
    return row[index]
