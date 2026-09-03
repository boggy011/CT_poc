"""Delta housekeeping for the per-request insert churn (plan step B11). ``python -m retpack_jobs.maintenance``."""

import logging
import os
import sys

from retpack_adapters.sql.executor import SqlExecutor, check_identifier

logger = logging.getLogger(__name__)


def maintenance_statements(catalog: str, schema: str, *, vacuum_hours: int = 720) -> tuple[str, ...]:
    """OPTIMIZE then VACUUM the event table. ``vacuum_hours`` must respect the retention decision (NFR-06)."""
    table = f"{check_identifier(catalog)}.{check_identifier(schema)}.submission_event"
    return (f"OPTIMIZE {table}", f"VACUUM {table} RETAIN {int(vacuum_hours)} HOURS")


def run(executor: SqlExecutor, catalog: str, schema: str) -> int:
    """Execute the maintenance statements; returns how many ran."""
    statements = maintenance_statements(catalog, schema)
    for statement in statements:
        logger.info("running %s", statement.split(" RETAIN")[0])
        executor.execute(statement)
    return len(statements)


def main() -> int:
    """CLI entry using the app's settings."""
    from retpack_adapters import factory

    logging.basicConfig(level=logging.INFO)
    settings = factory.Settings.from_env(os.environ)
    settings.require("catalog", "schema", "warehouse_id")
    return 0 if run(factory._delta_executor(settings), settings.catalog, settings.schema) else 1  # noqa: SLF001


if __name__ == "__main__":
    sys.exit(main())
