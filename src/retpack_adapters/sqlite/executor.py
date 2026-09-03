"""``SqlExecutor`` over the standard-library ``sqlite3``."""

import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any


class SqliteExecutor:
    """Single shared connection guarded by a lock (Streamlit is multi-threaded)."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL") if str(path) != ":memory:" else None
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.Lock()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        """See ``SqlExecutor.query``."""
        with self._lock:
            return [tuple(r) for r in self._conn.execute(sql, list(params)).fetchall()]

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """See ``SqlExecutor.execute``."""
        with self._lock:
            cursor = self._conn.execute(sql, list(params))
            return cursor.rowcount if cursor.rowcount >= 0 else 0

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()
