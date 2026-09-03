"""Shared fixtures.

``backend`` parametrizes the contract and isolation suites over every
``SubmissionRepository`` implementation. Real backends are env-gated:
set ``RETPACK_TEST_DELTA=1`` / ``RETPACK_TEST_LAKEBASE=1`` to include them.
"""

import os
from pathlib import Path

import pytest

from retpack_adapters.attachments.local import LocalAttachmentStore
from retpack_adapters.mock.fixtures import load_reference
from retpack_adapters.mock.submissions import InMemorySubmissionRepository
from retpack_core.attachments import load_attachment_policy
from retpack_core.ports import AttachmentStore, ReferenceRepository, SubmissionRepository
from retpack_core.principal import Principal, Role

BACKENDS = ("mock", "delta", "lakebase")
MOCK_DATA = Path("config/mock")

CUSTOMER_A = Principal(email="anna@northsea-distribution.example", account_ids=frozenset({"A1", "A2"}), role=Role.CUSTOMER)
CUSTOMER_B = Principal(email="bram@rhine-logistics.example", account_ids=frozenset({"B1"}), role=Role.CUSTOMER)
NOBODY = Principal(email="nobody@x.example", account_ids=frozenset(), role=Role.CUSTOMER)
INTERNAL = Principal(email="ops1@abi.example", account_ids=frozenset(), role=Role.INTERNAL)
SYSTEM = Principal(email="cpi-dispatch@system.local", account_ids=frozenset(), role=Role.SYSTEM)


@pytest.fixture(params=BACKENDS)
def backend(request: pytest.FixtureRequest) -> str:
    name = str(request.param)
    if name != "mock" and not os.environ.get(f"RETPACK_TEST_{name.upper()}"):
        pytest.skip(f"{name} backend not configured (set RETPACK_TEST_{name.upper()}=1)")
    return name


@pytest.fixture
def repo(backend: str) -> SubmissionRepository:
    if backend == "mock":
        return InMemorySubmissionRepository()
    pytest.skip(f"{backend} SubmissionRepository adapter is wired in Phase B")


@pytest.fixture
def attachment_store(backend: str, tmp_path: Path) -> AttachmentStore:
    if backend == "mock":
        return LocalAttachmentStore(tmp_path / "att", policy=load_attachment_policy(Path("config/attachments.yaml")))
    pytest.skip(f"{backend} AttachmentStore adapter is wired in Phase B")


@pytest.fixture
def reference(backend: str) -> ReferenceRepository:
    if backend == "mock":
        return load_reference(MOCK_DATA)
    pytest.skip(f"{backend} ReferenceRepository adapter is wired in Phase B")
