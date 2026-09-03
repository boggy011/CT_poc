"""Provision portal users in the reference tables. Takes effect on the user's next page load; no redeploy.

    python -m retpack_adapters.users_cli list
    python -m retpack_adapters.users_cli add-internal EMAIL [EMAIL ...]
    python -m retpack_adapters.users_cli add-customer EMAIL ACCOUNT_ID [ACCOUNT_ID ...]
    python -m retpack_adapters.users_cli remove EMAIL

Reads the same environment as the app (RETPACK_CATALOG, RETPACK_REF_SCHEMA, DATABRICKS_WAREHOUSE_ID, profile).
In production these tables are ABI-owned views (input 4); this tool is for the dev stubs.
"""

import logging
import os
import sys

from retpack_adapters.factory import Settings
from retpack_adapters.sql import ReferenceTables
from retpack_adapters.sql.executor import SqlExecutor

logger = logging.getLogger(__name__)


def _valid_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or " " in email:
        raise SystemExit(f"not an email: {value!r}")
    return email


def list_users(db: SqlExecutor, t: ReferenceTables) -> list[tuple[str, str, str]]:
    """(email, role, accounts) for every provisioned user."""
    internal = {str(r[0]) for r in db.query(f"SELECT LOWER(email) FROM {t.internal_user}")}
    accounts: dict[str, list[str]] = {}
    for email, account in db.query(f"SELECT LOWER(email), account_id FROM {t.email_account} ORDER BY 1, 2"):
        accounts.setdefault(str(email), []).append(str(account))
    rows = [(e, "internal", "") for e in sorted(internal)]
    rows += [(e, "customer", ", ".join(a)) for e, a in sorted(accounts.items()) if e not in internal]
    return rows


def add_internal(db: SqlExecutor, t: ReferenceTables, emails: list[str]) -> None:
    """Add ABI-team users (idempotent)."""
    for email in map(_valid_email, emails):
        db.execute(f"DELETE FROM {t.internal_user} WHERE LOWER(email) = ?", [email])
        db.execute(f"INSERT INTO {t.internal_user} VALUES (?)", [email])
        logger.info("internal user %s provisioned", email)


def add_customer(db: SqlExecutor, t: ReferenceTables, email: str, account_ids: list[str]) -> None:
    """Map a customer email to one or more accounts (idempotent; accounts must exist)."""
    email = _valid_email(email)
    known = {str(r[0]) for r in db.query(f"SELECT account_id FROM {t.account}")}
    unknown = [a for a in account_ids if a not in known]
    if unknown:
        raise SystemExit(f"unknown account(s): {', '.join(unknown)}; known: {', '.join(sorted(known))}")
    for account in account_ids:
        db.execute(f"DELETE FROM {t.email_account} WHERE LOWER(email) = ? AND account_id = ?", [email, account])
        db.execute(f"INSERT INTO {t.email_account} VALUES (?, ?)", [email, account])
    logger.info("customer %s mapped to %s", email, ", ".join(account_ids))


def remove(db: SqlExecutor, t: ReferenceTables, email: str) -> None:
    """Remove a user from both tables."""
    email = _valid_email(email)
    db.execute(f"DELETE FROM {t.internal_user} WHERE LOWER(email) = ?", [email])
    db.execute(f"DELETE FROM {t.email_account} WHERE LOWER(email) = ?", [email])
    logger.info("%s removed", email)


def run(db: SqlExecutor, t: ReferenceTables, argv: list[str]) -> int:
    """Dispatch one command; returns an exit code."""
    if not argv or argv[0] not in ("list", "add-internal", "add-customer", "remove"):
        print(__doc__, file=sys.stderr)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        for email, role, accounts in list_users(db, t):
            print(f"{email:45} {role:9} {accounts}")
    elif cmd == "add-internal":
        add_internal(db, t, args)
    elif cmd == "add-customer":
        if len(args) < 2:
            print(__doc__, file=sys.stderr)
            return 2
        add_customer(db, t, args[0], args[1:])
    else:
        remove(db, t, args[0])
    return 0


def main(argv: list[str]) -> int:
    """CLI entry against the workspace reference tables."""
    from retpack_adapters import factory

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logger.setLevel(logging.INFO)
    settings = Settings.from_env(os.environ)
    settings.require("catalog", "warehouse_id")
    tables = ReferenceTables.in_schema(f"{settings.catalog}.{settings.ref_schema}")
    return run(factory._delta_executor(settings), tables, argv[1:])  # noqa: SLF001


if __name__ == "__main__":
    sys.exit(main(sys.argv))
