"""Demo impersonation: only a verified internal user, only when enabled, always audited."""

import json
import logging
from pathlib import Path

import pytest

from retpack_adapters.attachments.memory_files import InMemoryFilesClient
from retpack_adapters.factory import Container, Settings, build_container
from retpack_adapters.sql.migrate import apply_files, migration_files
from retpack_adapters.sqlite.executor import SqliteExecutor
from retpack_adapters.sqlite.seed import seed_reference_tables
from retpack_core.principal import Principal, Role
from retpack_ui.state import effective_principal, show_switcher

ANNA = "anna@northsea-distribution.example"
OPS = "ops1@abi.example"
ME = "bogdan@ct.example"


class Unqualified:
    """SQLite stand-in for a workspace executor: drops the ``catalog.schema.`` prefix the factory adds."""

    def __init__(self, db: SqliteExecutor) -> None:
        self._db = db

    def query(self, sql: str, params=()):
        return self._db.query(sql.replace("c.retpack.", ""), params)

    def execute(self, sql: str, params=()) -> int:
        return self._db.execute(sql.replace("c.retpack.", ""), params)


def workspace_container(flag: str) -> Container:
    db = SqliteExecutor()
    apply_files(db, migration_files(Path("migrations/sqlite")), {})
    seed_reference_tables(db, Path("config/mock"))
    db.execute("INSERT INTO ref_internal_user (email) VALUES (?)", [ME])
    env = {"RETPACK_SUBMISSION_BACKEND": "delta", "RETPACK_CATALOG": "c", "DATABRICKS_WAREHOUSE_ID": "w", "RETPACK_DEMO_IMPERSONATION": flag}
    return build_container(Settings.from_env(env), executors={"delta": lambda: Unqualified(db)}, files_client=InMemoryFilesClient())


def test_flag_off_means_no_demo_users_and_no_switcher():
    c = workspace_container("0")
    assert c.demo_mode == "off" and c.demo_users == ()
    assert show_switcher(c, ME, True) is False
    real = Principal(email=ME, account_ids=frozenset(), role=Role.INTERNAL)
    assert effective_principal(c, real, ANNA) is real


def test_flag_on_lists_provisioned_users_and_offers_switcher_to_internal_only():
    c = workspace_container("1")
    assert c.demo_mode == "impersonate" and ANNA in c.demo_users and OPS in c.demo_users and ME in c.demo_users
    assert show_switcher(c, ME, True) is True
    assert show_switcher(c, ANNA, False) is False
    assert show_switcher(c, None, False) is False


def test_internal_user_can_view_as_customer_and_it_is_audited(caplog: pytest.LogCaptureFixture):
    c = workspace_container("1")
    real = Principal(email=ME, account_ids=frozenset(), role=Role.INTERNAL)
    with caplog.at_level(logging.INFO, logger="retpack.audit"):
        viewed = effective_principal(c, real, ANNA)
    assert viewed is not None and viewed.email == ANNA and viewed.role is Role.CUSTOMER and viewed.account_ids == frozenset({"A1", "A2"})
    record = json.loads(caplog.records[-1].getMessage())
    assert record["event"] == "demo_impersonation" and record["actor"] == ME and record["viewing_as"] == ANNA


def test_customer_can_never_impersonate():
    c = workspace_container("1")
    real = Principal(email=ANNA, account_ids=frozenset({"A1", "A2"}), role=Role.CUSTOMER)
    assert effective_principal(c, real, OPS) is real
    assert effective_principal(c, real, "bram@rhine-logistics.example") is real


def test_unknown_or_self_override_falls_back_to_real():
    c = workspace_container("1")
    real = Principal(email=ME, account_ids=frozenset(), role=Role.INTERNAL)
    assert effective_principal(c, real, "ghost@nowhere.example") is real
    assert effective_principal(c, real, ME.upper()) is real
    assert effective_principal(c, None, ANNA) is None


def test_local_backends_keep_header_mode(tmp_path: Path):
    c = build_container(Settings.from_env({"RETPACK_ATTACHMENT_DIR": str(tmp_path)}))
    assert c.demo_mode == "header" and show_switcher(c, None, False) is True
