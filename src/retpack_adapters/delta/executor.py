"""``SqlExecutor`` over ``databricks-sql-connector``.

MERGE statements return a single result row with ``num_inserted_rows``; that
is what ``execute`` reports so the shared repository can detect a lost race.
Delta's optimistic concurrency surfaces as a ``ServerOperationError`` whose
message names a concurrent-modification exception; those are retried a few
times with backoff before giving up.
"""

import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol, TypeVar

logger = logging.getLogger(__name__)

CONCURRENT_MARKERS = ("CONCURRENT_APPEND", "CONCURRENTAPPEND", "CONCURRENT_TRANSACTION", "CONCURRENT_WRITE", "CONCURRENTWRITE", "DELTA_CONCURRENT")
SESSION_MARKERS = ("INVALIDSESSIONHANDLE", "SESSIONISCLOSED", "SESSIONHANDLE", "SESSION_EXPIRED")
"""A warehouse invalidates idle sessions (e.g. overnight); such errors mean reconnect, not fail."""
MAX_ATTEMPTS = 3
BACKOFF_S = 0.2
T = TypeVar("T")


class _Cursor(Protocol):
    def execute(self, sql: str, params: Any = None) -> Any: ...
    def fetchall(self) -> list[Any]: ...
    def fetchone(self) -> Any: ...
    def close(self) -> None: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...


class DeltaExecutor:
    """One connection per executor, guarded by a lock (Streamlit is multi-threaded).

    A stale warehouse session (idle timeout, warehouse restart) is transparently
    replaced: the statement is retried once on a fresh connection.
    """

    def __init__(self, connect: Callable[[], _Connection]) -> None:
        self._connect = connect
        self._conn: _Connection | None = None
        self._lock = threading.Lock()

    def _cursor(self) -> _Cursor:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn.cursor()

    def _reset(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                close = getattr(conn, "close", None)
                if close is not None:
                    close()
            except Exception as exc:  # noqa: BLE001 - closing a dead connection is best effort
                logger.debug("ignoring error while closing stale connection: %s", exc)

    def _with_session_retry(self, action: Callable[[], T]) -> T:
        try:
            return action()
        except Exception as exc:
            if not is_session_error(exc):
                raise
            logger.warning("warehouse session expired; reconnecting: %s", type(exc).__name__)
            self._reset()
            return action()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        """See ``SqlExecutor.query``."""
        with self._lock:
            return self._with_session_retry(lambda: self._query_once(sql, params))

    def _query_once(self, sql: str, params: Sequence[Any]) -> list[tuple[Any, ...]]:
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
                with self._lock:
                    return self._with_session_retry(lambda: self._execute_once(sql, params))
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


def is_session_error(exc: BaseException) -> bool:
    """True if a connector error means the warehouse session is gone and a reconnect will help."""
    text = str(exc).upper().replace(" ", "")
    return any(marker in text for marker in SESSION_MARKERS)


def _field(row: Any, name: str, index: int) -> Any:
    if hasattr(row, "asDict"):
        return row.asDict()[name]
    if isinstance(row, dict):
        return row[name]
    return row[index]
