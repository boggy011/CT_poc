from pathlib import Path

import pytest

from retpack_adapters.factory import Container, Settings, build_container
from retpack_core.errors import ConfigError
from retpack_core.models import Status
from retpack_core.principal import Principal, Role


def test_settings_from_env_defaults():
    s = Settings.from_env({})
    assert s.backend == "mock"
    assert s.field_spec_path == Path("config/fields/placeholder.yaml")
    assert s.attachment_policy_path == Path("config/attachments.yaml")
    assert s.mock_data_dir == Path("config/mock")
    assert s.seed_demo is False


def test_settings_from_env_overrides(tmp_path: Path):
    env = {
        "RETPACK_SUBMISSION_BACKEND": "delta",
        "RETPACK_FIELD_SPEC": str(tmp_path / "f.yaml"),
        "RETPACK_ATTACHMENT_DIR": str(tmp_path / "a"),
        "RETPACK_MOCK_USER": "ops@abi.com",
        "RETPACK_MOCK_SEED": "1",
    }
    s = Settings.from_env(env)
    assert s.backend == "delta" and s.field_spec_path == tmp_path / "f.yaml" and s.attachment_dir == tmp_path / "a"
    assert s.mock_user == "ops@abi.com" and s.seed_demo is True


def test_unknown_backend_rejected():
    with pytest.raises(ConfigError, match="backend"):
        Settings.from_env({"RETPACK_SUBMISSION_BACKEND": "oracle"})


def test_build_mock_container_with_demo_seed(tmp_path: Path):
    c = build_container(Settings.from_env({"RETPACK_ATTACHMENT_DIR": str(tmp_path), "RETPACK_MOCK_SEED": "1"}))
    assert isinstance(c, Container) and c.backend == "mock"
    assert "anna@northsea-distribution.example" in c.demo_users
    internal = Principal(email="ops@abi.com", account_ids=frozenset(), role=Role.INTERNAL)
    subs = c.ports.submissions.list_submissions(internal)
    assert len(subs) >= 8
    assert {s.status for s in subs} >= {Status.SUBMITTED, Status.VALIDATED, Status.CPI_DONE, Status.CPI_FAILED}
    assert any(s.overwrites for s in subs)
    assert any(s.credit_note for s in subs)
    assert any(s.attachments for s in subs)
    # Every seeded submission belongs to an account that exists in the reference data.
    accounts = {a.account_id for a in c.ports.reference.my_accounts(internal)}
    assert {s.account_id for s in subs} <= accounts
    # Every seeded submission validates against the placeholder spec (so the internal queue can validate them).
    from retpack_core.fieldspec import validate_values
    from retpack_core.services import enum_options

    for s in subs:
        result = validate_values(s.values, c.spec, enum_options=enum_options(c.ports.reference, c.spec, internal, account_id=s.account_id))
        assert result.ok, (s.submission_id, result.errors)


def test_build_mock_container_without_seed(tmp_path: Path):
    c = build_container(Settings.from_env({"RETPACK_ATTACHMENT_DIR": str(tmp_path)}))
    internal = Principal(email="ops@abi.com", account_ids=frozenset(), role=Role.INTERNAL)
    assert c.ports.submissions.list_submissions(internal) == ()


def test_mock_users_resolve_through_identity(tmp_path: Path):
    c = build_container(Settings.from_env({"RETPACK_ATTACHMENT_DIR": str(tmp_path)}))
    p = c.identity.resolve({"X-Forwarded-Email": "anna@northsea-distribution.example"})
    assert p is not None and p.role is Role.CUSTOMER and p.account_ids
    ops = c.identity.resolve({"X-Forwarded-Email": "ops1@abi.example"})
    assert ops is not None and ops.role is Role.INTERNAL


def test_sqlite_backend_persists_between_containers(tmp_path: Path):
    env = {
        "RETPACK_SUBMISSION_BACKEND": "sqlite",
        "RETPACK_SQLITE_PATH": str(tmp_path / "db.sqlite"),
        "RETPACK_ATTACHMENT_DIR": str(tmp_path / "att"),
        "RETPACK_MOCK_SEED": "1",
    }
    c1 = build_container(Settings.from_env(env))
    internal = Principal(email="ops1@abi.example", account_ids=frozenset(), role=Role.INTERNAL)
    first = c1.ports.submissions.list_submissions(internal)
    assert len(first) == 11 and c1.backend == "sqlite" and c1.demo_users
    c2 = build_container(Settings.from_env(env))  # seed must not duplicate
    assert len(c2.ports.submissions.list_submissions(internal)) == 11
    anna = c2.identity.resolve({"X-Forwarded-Email": "anna@northsea-distribution.example"})
    assert anna is not None and anna.account_ids == frozenset({"A1", "A2"})
    assert c2.ports.reference.keg_balance(anna, "A1") is not None


def test_workspace_backend_requires_settings():
    with pytest.raises(ConfigError, match="catalog"):
        build_container(Settings.from_env({"RETPACK_SUBMISSION_BACKEND": "delta"}))
    with pytest.raises(ConfigError, match="lakebase_instance"):
        build_container(
            Settings.from_env({"RETPACK_SUBMISSION_BACKEND": "lakebase", "RETPACK_CATALOG": "c", "DATABRICKS_WAREHOUSE_ID": "w"}),
            executors={"delta": lambda: None},  # type: ignore[dict-item]
        )


def test_workspace_backends_wire_sql_repos_volume_store_and_apps_identity(tmp_path: Path):
    from retpack_adapters.attachments.memory_files import InMemoryFilesClient
    from retpack_adapters.attachments.volume import VolumeAttachmentStore
    from retpack_adapters.identity.databricks_apps import DatabricksAppsIdentityProvider
    from retpack_adapters.sql import SqlSubmissionRepository
    from retpack_adapters.sql.migrate import apply_files, migration_files
    from retpack_adapters.sqlite.executor import SqliteExecutor

    db = SqliteExecutor()
    apply_files(db, migration_files(Path("migrations/sqlite")), {})
    env = {"RETPACK_SUBMISSION_BACKEND": "lakebase", "RETPACK_CATALOG": "c", "DATABRICKS_WAREHOUSE_ID": "w", "RETPACK_LAKEBASE_INSTANCE": "lb"}
    c = build_container(Settings.from_env(env), executors={"delta": lambda: db, "lakebase": lambda: db}, files_client=InMemoryFilesClient())
    assert isinstance(c.ports.submissions, SqlSubmissionRepository)
    assert isinstance(c.ports.attachments, VolumeAttachmentStore)
    assert isinstance(c.identity, DatabricksAppsIdentityProvider)
    assert c.demo_users == ()
    assert c.settings.volume_root == "/Volumes/c/retpack/attachments"
