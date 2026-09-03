from datetime import UTC, datetime
from pathlib import Path

import pytest

from retpack_adapters.mock.reference import InMemoryReferenceRepository
from retpack_adapters.mock.submissions import InMemorySubmissionRepository
from retpack_core.attachments import load_attachment_policy
from retpack_core.fieldspec import load_form_spec
from retpack_core.models import Account, KegBalance, SalesOrg, Sku
from retpack_core.ports import Ports
from retpack_core.principal import Principal, Role
from retpack_core.services import IntakeService, QueryService, ReviewService
from tests.unit.fakes import RecordingAttachmentStore

CUSTOMER_A = Principal(email="a@dist.com", account_ids=frozenset({"A1", "A2"}), role=Role.CUSTOMER)
CUSTOMER_B = Principal(email="b@dist.com", account_ids=frozenset({"B1"}), role=Role.CUSTOMER)
INTERNAL = Principal(email="ops@abi.com", account_ids=frozenset(), role=Role.INTERNAL)
SYSTEM = Principal(email="cpi-dispatch@system.local", account_ids=frozenset(), role=Role.SYSTEM)

VALID_VALUES = {
    "account_id": "A1",
    "sku_code": "KEG50",
    "container_no": "1234567890",
    "bl_no": "BL-77",
    "destination": "Antwerp",
    "quantity": 12,
    "pickup_date": "2026-09-10",
}


@pytest.fixture
def reference() -> InMemoryReferenceRepository:
    now = datetime(2026, 9, 3, tzinfo=UTC)
    return InMemoryReferenceRepository(
        accounts=[
            Account(account_id="A1", name="Dist A one", sales_org="1000"),
            Account(account_id="A2", name="Dist A two", sales_org="1000"),
            Account(account_id="B1", name="Dist B", sales_org="2000"),
        ],
        skus=[
            Sku(account_id="A1", sku_code="KEG50", description="50L"),
            Sku(account_id="A1", sku_code="KEG30", description="30L"),
            Sku(account_id="B1", sku_code="KEG20", description="20L"),
        ],
        sales_orgs=[SalesOrg(code="1000", name="BE"), SalesOrg(code="2000", name="NL")],
        balances=[KegBalance(account_id="A1", shipped=100, returned=60, as_of=now), KegBalance(account_id="B1", shipped=10, returned=0, as_of=now)],
    )


@pytest.fixture
def store() -> RecordingAttachmentStore:
    return RecordingAttachmentStore()


@pytest.fixture
def ports(reference: InMemoryReferenceRepository, store: RecordingAttachmentStore) -> Ports:
    return Ports(submissions=InMemorySubmissionRepository(), reference=reference, attachments=store)


@pytest.fixture
def spec():
    return load_form_spec(Path("config/fields/placeholder.yaml"))


@pytest.fixture
def policy():
    return load_attachment_policy(Path("config/attachments.yaml"))


@pytest.fixture
def intake(ports: Ports, spec, policy) -> IntakeService:
    return IntakeService(ports, spec, policy)


@pytest.fixture
def review(ports: Ports, spec) -> ReviewService:
    return ReviewService(ports, spec)


@pytest.fixture
def query(ports: Ports) -> QueryService:
    return QueryService(ports)
