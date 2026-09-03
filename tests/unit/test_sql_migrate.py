from pathlib import Path

import pytest

from retpack_adapters.sql.migrate import apply_files, migration_files, render, split_statements
from retpack_adapters.sqlite.executor import SqliteExecutor


def test_render_substitutes_and_rejects_unknown():
    assert render("CREATE TABLE ${catalog}.${schema}.t", {"catalog": "c", "schema": "s"}) == "CREATE TABLE c.s.t"
    with pytest.raises(KeyError):
        render("${nope}", {})


def test_split_statements_drops_comments_and_blank():
    sql = "-- header\nCREATE TABLE a (x INT);\n\n-- note\nCREATE INDEX i ON a (x);\nSELECT 1"
    assert split_statements(sql) == ["CREATE TABLE a (x INT)", "CREATE INDEX i ON a (x)", "SELECT 1"]


def test_sqlite_migrations_apply_idempotently():
    db = SqliteExecutor()
    files = migration_files(Path("migrations/sqlite"))
    assert len(files) == 2
    n1 = apply_files(db, files, {})
    n2 = apply_files(db, files, {})
    assert n1 == n2 > 0
    tables = {r[0] for r in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"submission_event", "ref_account", "ref_sku", "ref_sales_org", "ref_email_account", "ref_internal_user", "keg_balance"} <= tables


@pytest.mark.parametrize("directory", ["migrations/delta", "migrations/lakebase"])
def test_real_backend_migrations_render_without_unknown_placeholders(directory: str):
    variables = {"catalog": "cat", "schema": "retpack", "ref_schema": "ref"}
    for path in migration_files(Path(directory)):
        statements = split_statements(render(path.read_text(), variables))
        assert statements, path
        assert all("${" not in s for s in statements), path
