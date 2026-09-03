"""Load the mock reference JSON into the SQLite reference tables (idempotent)."""

from pathlib import Path

from retpack_adapters.mock.fixtures import load_directory, load_reference
from retpack_adapters.sql.executor import SqlExecutor
from retpack_adapters.sql.reference import ReferenceTables
from retpack_core.principal import Principal, Role

_ALL = Principal(email="seed@system.local", account_ids=frozenset(), role=Role.SYSTEM)


def seed_reference_tables(executor: SqlExecutor, data_dir: Path, tables: ReferenceTables | None = None) -> None:
    """Upsert accounts, SKUs, sales orgs, balances and users from ``data_dir``."""
    t = tables or ReferenceTables()
    ref = load_reference(data_dir)
    for a in ref.my_accounts(_ALL):
        executor.execute(f"INSERT OR REPLACE INTO {t.account} (account_id, name, sales_org) VALUES (?, ?, ?)", [a.account_id, a.name, a.sales_org])
        for s in ref.skus_for_account(_ALL, a.account_id):
            executor.execute(f"INSERT OR REPLACE INTO {t.sku} (account_id, sku_code, description) VALUES (?, ?, ?)", [s.account_id, s.sku_code, s.description])
        balance = ref.keg_balance(_ALL, a.account_id)
        if balance is not None:
            executor.execute(
                f"INSERT OR REPLACE INTO {t.keg_balance} (account_id, shipped, returned, as_of) VALUES (?, ?, ?, ?)",
                [balance.account_id, balance.shipped, balance.returned, balance.as_of.isoformat()],
            )
    for so in ref.sales_orgs(_ALL):
        executor.execute(f"INSERT OR REPLACE INTO {t.sales_org} (code, name) VALUES (?, ?)", [so.code, so.name])
    directory = load_directory(data_dir)
    for email in _emails(data_dir):
        if directory.is_internal(email):
            executor.execute(f"INSERT OR REPLACE INTO {t.internal_user} (email) VALUES (?)", [email.lower()])
        for account_id in directory.account_ids_for_email(email):
            executor.execute(f"INSERT OR REPLACE INTO {t.email_account} (email, account_id) VALUES (?, ?)", [email.lower(), account_id])


def _emails(data_dir: Path) -> tuple[str, ...]:
    from retpack_adapters.mock.fixtures import list_user_emails

    return list_user_emails(data_dir)
