"""Pin the service to the real local store and real PDFs so the unit fakes cannot drift."""

from io import BytesIO
from pathlib import Path

import pytest

from retpack_adapters.attachments.local import LocalAttachmentStore
from retpack_adapters.mock.submissions import InMemorySubmissionRepository
from retpack_core.attachments import load_attachment_policy
from retpack_core.errors import InvalidAttachmentError, ValidationFailedError
from retpack_core.fieldspec import load_form_spec
from retpack_core.ports import Ports
from retpack_core.services import IntakeService, UploadedPdf
from tests.unit.conftest import CUSTOMER_A, VALID_VALUES

SAMPLE = Path("tests/fixtures/sample.pdf").read_bytes()
SCANNED = Path("tests/fixtures/scanned.pdf").read_bytes()


@pytest.fixture
def service(tmp_path: Path, reference):
    policy = load_attachment_policy(Path("config/attachments.yaml"))
    ports = Ports(submissions=InMemorySubmissionRepository(), reference=reference, attachments=LocalAttachmentStore(tmp_path, policy=policy))
    return IntakeService(ports, load_form_spec(Path("config/fields/placeholder.yaml")), policy)


def test_real_pdfs_round_trip(service: IntakeService, tmp_path: Path):
    uploads = [
        UploadedPdf(doc_type="delivery_note", filename="dn.pdf", stream=BytesIO(SAMPLE)),
        UploadedPdf(doc_type="other", filename="scan.pdf", stream=BytesIO(SCANNED)),
    ]
    result = service.submit(CUSTOMER_A, VALID_VALUES, uploads)
    metas = result.submission.attachments
    assert [m.has_text_layer for m in metas] == [True, False]
    assert result.warnings == ("scan.pdf has no text layer; the automated cross-check cannot read it",)
    assert all(Path(m.storage_path).is_file() for m in metas)
    assert all(Path(m.storage_path).is_relative_to(tmp_path / "A1") for m in metas)


def test_corrupt_second_file_leaves_no_orphans(service: IntakeService, tmp_path: Path):
    uploads = [
        UploadedPdf(doc_type="delivery_note", filename="dn.pdf", stream=BytesIO(SAMPLE)),
        UploadedPdf(doc_type="other", filename="bad.pdf", stream=BytesIO(b"%PDF-1.4 garbage")),
    ]
    with pytest.raises(InvalidAttachmentError):
        service.submit(CUSTOMER_A, VALID_VALUES, uploads)
    assert not list(tmp_path.rglob("*.pdf"))


def test_non_pdf_is_a_validation_error_before_anything_is_stored(service: IntakeService, tmp_path: Path):
    with pytest.raises(ValidationFailedError):
        service.submit(CUSTOMER_A, VALID_VALUES, [UploadedPdf(doc_type="delivery_note", filename="x.pdf", stream=BytesIO(b"GIF89a"))])
    assert not list(tmp_path.rglob("*"))
