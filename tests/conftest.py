"""Shared fixtures.

``backend`` parametrizes the contract and isolation suites over every
``SubmissionRepository`` implementation. ``mock`` and ``sqlite`` always run;
``delta`` and ``lakebase`` are env-gated: set ``RETPACK_TEST_DELTA=1`` /
``RETPACK_TEST_LAKEBASE=1`` (plus the connection settings the factory reads)
to include them.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from retpack_adapters.attachments.local import LocalAttachmentStore
from retpack_adapters.attachments.memory_files import InMemoryFilesClient
from retpack_adapters.attachments.volume import VolumeAttachmentStore
from retpack_adapters.mock.fixtures import load_reference
from retpack_adapters.mock.submissions import InMemorySubmissionRepository
from retpack_adapters.sql import SqlReferenceRepository, SqlSubmissionRepository
from retpack_adapters.sql.executor import sqlite_dialect
from retpack_adapters.sql.migrate import apply_files, migration_files
from retpack_adapters.sqlite.executor import SqliteExecutor
from retpack_adapters.sqlite.seed import seed_reference_tables
from retpack_core.attachments import load_attachment_policy
from retpack_core.ports import AttachmentStore, ReferenceRepository, SubmissionRepository
from retpack_core.principal import Principal, Role

BACKENDS = ("mock", "sqlite", "delta", "lakebase")
MOCK_DATA = Path("config/mock")
POLICY = Path("config/attachments.yaml")

CUSTOMER_A = Principal(email="anna@northsea-distribution.example", account_ids=frozenset({"A1", "A2"}), role=Role.CUSTOMER)
CUSTOMER_B = Principal(email="bram@rhine-logistics.example", account_ids=frozenset({"B1"}), role=Role.CUSTOMER)
NOBODY = Principal(email="nobody@x.example", account_ids=frozenset(), role=Role.CUSTOMER)
INTERNAL = Principal(email="ops1@abi.example", account_ids=frozenset(), role=Role.INTERNAL)
SYSTEM = Principal(email="cpi-dispatch@system.local", account_ids=frozenset(), role=Role.SYSTEM)


@pytest.fixture(params=BACKENDS)
def backend(request: pytest.FixtureRequest) -> str:
    name = str(request.param)
    if name in ("delta", "lakebase") and not os.environ.get(f"RETPACK_TEST_{name.upper()}"):
        pytest.skip(f"{name} backend not configured (set RETPACK_TEST_{name.upper()}=1)")
    return name


@pytest.fixture
def sqlite_db() -> Iterator[SqliteExecutor]:
    db = SqliteExecutor()
    apply_files(db, migration_files(Path("migrations/sqlite")), {})
    seed_reference_tables(db, MOCK_DATA)
    yield db
    db.close()


@pytest.fixture
def repo(backend: str, sqlite_db: SqliteExecutor) -> SubmissionRepository:
    if backend == "mock":
        return InMemorySubmissionRepository()
    if backend == "sqlite":
        return SqlSubmissionRepository(sqlite_db, sqlite_dialect())
    from retpack_adapters.factory import Settings, build_container

    return build_container(Settings.from_env(os.environ)).ports.submissions


@pytest.fixture
def reference(backend: str, sqlite_db: SqliteExecutor) -> ReferenceRepository:
    if backend == "mock":
        return load_reference(MOCK_DATA)
    if backend == "sqlite":
        return SqlReferenceRepository(sqlite_db)
    from retpack_adapters.factory import Settings, build_container

    return build_container(Settings.from_env(os.environ)).ports.reference


@pytest.fixture(params=["local", "volume"])
def attachment_store(request: pytest.FixtureRequest, tmp_path: Path) -> AttachmentStore:
    policy = load_attachment_policy(POLICY)
    if request.param == "local":
        return LocalAttachmentStore(tmp_path / "att", policy=policy)
    return VolumeAttachmentStore(InMemoryFilesClient(), root="/Volumes/cat/retpack/attachments", policy=policy, spool_dir=tmp_path / "spool")
