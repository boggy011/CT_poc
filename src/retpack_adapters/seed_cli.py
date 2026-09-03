"""Seed a DEV workspace schema: reference stub tables from config/mock and the demo submissions.

``python -m retpack_adapters.seed_cli [--no-demo] [--extra-internal EMAIL ...]``. Never run against production reference views.
"""

import logging
import os
import sys
from pathlib import Path

from retpack_adapters.factory import Settings, build_container
from retpack_adapters.mock.fixtures import list_user_emails, load_directory, load_reference
from retpack_adapters.mock.seed import seed_demo
from retpack_adapters.sql import ReferenceTables
from retpack_adapters.sql.executor import SqlExecutor
from retpack_core.principal import Principal, Role

logger = logging.getLogger(__name__)
_ALL = Principal(email="seed@system.local", account_ids=frozenset(), role=Role.SYSTEM)


def seed_reference(executor: SqlExecutor, tables: ReferenceTables, data_dir: Path, extra_internal: list[str]) -> None:
    """Replace the contents of the dev stub tables with the mock fixtures (plus extra internal emails)."""
    ref = load_reference(data_dir)
    directory = load_directory(data_dir)
    for table in (tables.account, tables.sku, tables.sales_org, tables.keg_balance, tables.email_account, tables.internal_user):
        executor.execute(f"DELETE FROM {table}")
    for a in ref.my_accounts(_ALL):
        executor.execute(f"INSERT INTO {tables.account} VALUES (?, ?, ?)", [a.account_id, a.name, a.sales_org])
        for s in ref.skus_for_account(_ALL, a.account_id):
            executor.execute(f"INSERT INTO {tables.sku} VALUES (?, ?, ?)", [s.account_id, s.sku_code, s.description])
        balance = ref.keg_balance(_ALL, a.account_id)
        if balance is not None:
            executor.execute(f"INSERT INTO {tables.keg_balance} VALUES (?, ?, ?, ?)", [balance.account_id, balance.shipped, balance.returned, balance.as_of])
    for so in ref.sales_orgs(_ALL):
        executor.execute(f"INSERT INTO {tables.sales_org} VALUES (?, ?)", [so.code, so.name])
    for email in list_user_emails(data_dir):
        if directory.is_internal(email):
            executor.execute(f"INSERT INTO {tables.internal_user} VALUES (?)", [email.lower()])
        for account_id in directory.account_ids_for_email(email):
            executor.execute(f"INSERT INTO {tables.email_account} VALUES (?, ?)", [email.lower(), account_id])
    for email in extra_internal:
        executor.execute(f"INSERT INTO {tables.internal_user} VALUES (?)", [email.lower()])


def main(argv: list[str]) -> int:
    """Seed reference stubs and, unless ``--no-demo``, the demo submissions through the real repositories."""
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env(os.environ)
    if settings.backend not in ("delta", "lakebase"):
        print("seed_cli targets a workspace backend", file=sys.stderr)
        return 2
    from retpack_adapters import factory

    extra = [a for a in argv[1:] if "@" in a]
    delta = factory._delta_executor(settings)  # noqa: SLF001
    tables = ReferenceTables.in_schema(f"{settings.catalog}.{settings.ref_schema}")
    seed_reference(delta, tables, settings.mock_data_dir, extra)
    logger.info("reference stub tables seeded in %s.%s", settings.catalog, settings.ref_schema)
    if "--no-demo" not in argv:
        container = build_container(settings)
        seed_demo(container.ports.submissions, container.ports.attachments, settings.mock_data_dir)
        logger.info("demo submissions seeded")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
