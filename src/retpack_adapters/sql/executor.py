"""Executor protocol and per-engine dialects."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

EVENT_COLUMNS = ("submission_id", "account_id", "seq", "event_type", "actor", "actor_role", "occurred_at", "payload", "ingested_at")


class SqlExecutor(Protocol):
    """Runs parameterised statements. ``?`` is the placeholder in every statement handed to it."""

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        """Run a SELECT and return all rows as tuples."""
        ...

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Run a statement and return the number of rows inserted or affected."""
        ...


def check_identifier(name: str) -> str:
    """Allow only plain identifiers in interpolated table names (configuration, never user input)."""
    for part in name.split("."):
        if not _IDENT.match(part):
            raise ValueError(f"unsafe SQL identifier {name!r}")
    return name


@dataclass(frozen=True)
class Dialect:
    """Engine-specific pieces. Everything else in the repositories is portable SQL."""

    name: str
    event_table: str
    insert_event_sql: str
    """Insert one event row; must insert nothing (and report 0) if (submission_id, seq) already exists."""
    timestamps_as_text: bool = False
    """SQLite has no timestamp type; store ISO-8601 UTC strings and compare lexically."""

    def __post_init__(self) -> None:
        """Validate the interpolated table name."""
        check_identifier(self.event_table)


def _insert_columns() -> str:
    return ", ".join(EVENT_COLUMNS)


def _insert_markers() -> str:
    return ", ".join("?" for _ in EVENT_COLUMNS)


def sqlite_dialect(event_table: str = "submission_event") -> Dialect:
    """SQLite: ``INSERT OR IGNORE`` reports 0 rows on a primary-key clash."""
    return Dialect(
        name="sqlite",
        event_table=event_table,
        insert_event_sql=f"INSERT OR IGNORE INTO {check_identifier(event_table)} ({_insert_columns()}) VALUES ({_insert_markers()})",
        timestamps_as_text=True,
    )


def lakebase_dialect(schema: str) -> Dialect:
    """Postgres: ``ON CONFLICT DO NOTHING`` on the (submission_id, seq) primary key."""
    table = f"{check_identifier(schema)}.submission_event"
    return Dialect(
        name="lakebase",
        event_table=table,
        insert_event_sql=f"INSERT INTO {table} ({_insert_columns()}) VALUES ({_insert_markers()}) ON CONFLICT (submission_id, seq) DO NOTHING",
    )


def delta_dialect(catalog: str, schema: str) -> Dialect:
    """Delta: conditional MERGE; the executor returns ``num_inserted_rows`` from the MERGE result."""
    table = f"{check_identifier(catalog)}.{check_identifier(schema)}.submission_event"
    aliased = ", ".join(f"? AS {c}" for c in EVENT_COLUMNS)
    values = ", ".join(f"s.{c}" for c in EVENT_COLUMNS)
    return Dialect(
        name="delta",
        event_table=table,
        insert_event_sql=(
            f"MERGE INTO {table} t USING (SELECT {aliased}) s "
            "ON t.submission_id = s.submission_id AND t.seq = s.seq "
            f"WHEN NOT MATCHED THEN INSERT ({_insert_columns()}) VALUES ({values})"
        ),
    )
