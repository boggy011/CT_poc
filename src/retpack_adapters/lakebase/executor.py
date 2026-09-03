"""``SqlExecutor`` over psycopg 3.

Statements arrive with ``?`` placeholders and are translated to ``%s``. The
connection is autocommit (every append is a single statement). Lakebase
credentials are short-lived OAuth tokens, so a failed statement on an
``OperationalError`` reconnects once with a fresh connection.
"""

import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class _Cursor(Protocol):
    rowcount: int

    def execute(self, sql: str, params: Any = None) -> Any: ...
    def fetchall(self) -> list[Any]: ...
    def __enter__(self) -> "_Cursor": ...
    def __exit__(self, *exc: object) -> None: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...
    def close(self) -> None: ...


def translate_placeholders(sql: str) -> str:
    """``?`` to ``%s``. Statements never contain a literal question mark."""
    return sql.replace("?", "%s")


class LakebaseExecutor:
    """Reconnecting executor; ``connect`` must return an autocommit connection."""

    def __init__(self, connect: Callable[[], _Connection], *, operational_error: type[BaseException] | None = None) -> None:
        self._connect = connect
        self._conn: _Connection | None = None
        self._operational_error = operational_error or _default_operational_error()

    def _connection(self) -> _Connection:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def _reset(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception as exc:  # noqa: BLE001 - closing a broken connection is best effort
                logger.debug("ignoring error while closing broken connection: %s", exc)
        self._conn = None

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        """See ``SqlExecutor.query``."""
        rows: list[tuple[Any, ...]] = self._run(sql, params, fetch=True)
        return rows

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """See ``SqlExecutor.execute``."""
        result = self._run(sql, params, fetch=False)
        return int(result)

    def _run(self, sql: str, params: Sequence[Any], *, fetch: bool) -> Any:
        translated = translate_placeholders(sql)
        for attempt in (1, 2):
            try:
                with self._connection().cursor() as cur:
                    cur.execute(translated, list(params))
                    if fetch:
                        return [tuple(r) for r in cur.fetchall()]
                    return cur.rowcount if cur.rowcount >= 0 else 0
            except self._operational_error as exc:
                if attempt == 2:
                    raise
                logger.warning("Lakebase connection failed, reconnecting: %s", exc)
                self._reset()
        raise AssertionError("unreachable")


def _default_operational_error() -> type[BaseException]:
    try:
        import psycopg

        return psycopg.OperationalError
    except ImportError:  # psycopg is an optional extra
        return ConnectionError
