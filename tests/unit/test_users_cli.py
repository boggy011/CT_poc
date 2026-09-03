from pathlib import Path

import pytest

from retpack_adapters.sql import ReferenceTables, SqlAccountDirectory
from retpack_adapters.sql.migrate import apply_files, migration_files
from retpack_adapters.sqlite.executor import SqliteExecutor
from retpack_adapters.sqlite.seed import seed_reference_tables
from retpack_adapters.users_cli import add_customer, add_internal, remove, run


@pytest.fixture
def db() -> SqliteExecutor:
    db = SqliteExecutor()
    apply_files(db, migration_files(Path("migrations/sqlite")), {})
    seed_reference_tables(db, Path("config/mock"))
    return db


def test_add_internal_is_idempotent_and_visible_to_directory(db: SqliteExecutor):
    t = ReferenceTables()
    add_internal(db, t, ["New.Person@Example.com"])
    add_internal(db, t, ["new.person@example.com"])
    assert db.query("SELECT COUNT(*) FROM ref_internal_user WHERE email = 'new.person@example.com'")[0][0] == 1
    assert SqlAccountDirectory(db).is_internal("NEW.PERSON@example.com") is True


def test_add_customer_requires_known_accounts(db: SqliteExecutor):
    t = ReferenceTables()
    with pytest.raises(SystemExit, match="unknown account"):
        add_customer(db, t, "x@dist.example", ["ZZ"])
    add_customer(db, t, "x@dist.example", ["A1", "B1"])
    add_customer(db, t, "x@dist.example", ["A1"])  # idempotent
    assert SqlAccountDirectory(db).account_ids_for_email("x@dist.example") == frozenset({"A1", "B1"})


def test_list_and_remove(db: SqliteExecutor, capsys: pytest.CaptureFixture[str]):
    t = ReferenceTables()
    assert run(db, t, ["list"]) == 0
    out = capsys.readouterr().out
    assert "ops1@abi.example" in out and "anna@northsea-distribution.example" in out and "A1, A2" in out
    remove(db, t, "anna@northsea-distribution.example")
    assert SqlAccountDirectory(db).account_ids_for_email("anna@northsea-distribution.example") == frozenset()


def test_usage_on_bad_command(db: SqliteExecutor):
    assert run(db, ReferenceTables(), ["frobnicate"]) == 2
    assert run(db, ReferenceTables(), ["add-customer", "only@email.example"]) == 2


def test_rejects_non_email(db: SqliteExecutor):
    with pytest.raises(SystemExit):
        add_internal(db, ReferenceTables(), ["not an email"])
