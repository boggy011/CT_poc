"""Apply migrations for one backend. ``python -m retpack_adapters.migrate_cli delta|lakebase|sqlite``.

Reads the same environment variables as the app (see ``retpack_adapters.factory.Settings``).
"""

import logging
import os
import sys
from pathlib import Path

from retpack_adapters.factory import Settings
from retpack_adapters.sql.executor import SqlExecutor
from retpack_adapters.sql.migrate import apply_files, migration_files

logger = logging.getLogger(__name__)


def executor_for(backend: str, settings: Settings) -> SqlExecutor:
    """Build the executor for ``backend`` from settings."""
    if backend == "sqlite":
        from retpack_adapters.sqlite.executor import SqliteExecutor

        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteExecutor(settings.sqlite_path)
    from retpack_adapters import factory

    if backend == "delta":
        settings.require("catalog", "schema", "warehouse_id")
        return factory._delta_executor(settings)  # noqa: SLF001 - CLI is part of the adapters package
    settings.require("lakebase_instance")
    return factory._lakebase_executor(settings)  # noqa: SLF001


def _delta_file_enabled(name: str) -> bool:
    if "dev_stubs" in name:
        return os.environ.get("RETPACK_MIGRATE_DEV_STUBS") == "1"
    if "row_filters" in name:
        return os.environ.get("RETPACK_MIGRATE_ROW_FILTERS") == "1"
    return True


def main(argv: list[str]) -> int:
    """Run all ``migrations/<backend>/*.sql`` in order."""
    logging.basicConfig(level=logging.INFO)
    backend = argv[1] if len(argv) > 1 else "sqlite"
    if backend not in ("sqlite", "delta", "lakebase"):
        print(f"usage: {argv[0]} sqlite|delta|lakebase", file=sys.stderr)
        return 2
    settings = Settings.from_env(os.environ)
    variables = {"catalog": settings.catalog, "schema": settings.schema, "ref_schema": settings.ref_schema}
    files = migration_files(Path("migrations") / backend)
    if backend == "delta":
        files = [f for f in files if _delta_file_enabled(f.name)]
    count = apply_files(executor_for(backend, settings), files, variables)
    logger.info("applied %d statements from %d files for %s", count, len(files), backend)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
