from io import BytesIO
from pathlib import Path

import pytest

from retpack_adapters.attachments.local import LocalAttachmentStore
from retpack_core.errors import InvalidAttachmentError, NotFoundError
from retpack_core.models import AttachmentMeta
from tests.unit.conftest import CUSTOMER_A

SAMPLE = Path("tests/fixtures/sample.pdf").read_bytes()
SCANNED = Path("tests/fixtures/scanned.pdf").read_bytes()
SID = "0190f0a0-0000-7000-8000-000000000001"


@pytest.fixture
def store(tmp_path: Path) -> LocalAttachmentStore:
    return LocalAttachmentStore(tmp_path / "att", max_bytes=1_000_000)


def test_put_stores_and_returns_meta(store: LocalAttachmentStore, tmp_path: Path):
    meta = store.put(CUSTOMER_A, SID, doc_type="delivery_note", seq=1, filename="../evil/dn.pdf", stream=BytesIO(SAMPLE))
    assert meta.submission_id == SID
    assert meta.original_filename == "../evil/dn.pdf"
    assert meta.page_count == 1 and meta.has_text_layer is True
    assert meta.size_bytes == len(SAMPLE)
    assert meta.uploaded_by == "a@dist.com"
    stored = Path(meta.storage_path)
    assert stored.is_relative_to(tmp_path / "att")
    assert stored.name == "delivery_note_1.pdf"
    assert stored.read_bytes() == SAMPLE
    assert not list(stored.parent.glob("*.part"))


def test_put_scanned_sets_flag(store: LocalAttachmentStore):
    meta = store.put(CUSTOMER_A, SID, doc_type="other", seq=2, filename="scan.pdf", stream=BytesIO(SCANNED))
    assert meta.has_text_layer is False


def test_put_rejects_non_pdf_and_leaves_no_file(store: LocalAttachmentStore, tmp_path: Path):
    with pytest.raises(InvalidAttachmentError):
        store.put(CUSTOMER_A, SID, doc_type="other", seq=1, filename="x.pdf", stream=BytesIO(b"not a pdf"))
    assert not list((tmp_path / "att").rglob("*"))


def test_put_rejects_corrupt_pdf_and_cleans_up(store: LocalAttachmentStore, tmp_path: Path):
    with pytest.raises(InvalidAttachmentError):
        store.put(CUSTOMER_A, SID, doc_type="other", seq=1, filename="x.pdf", stream=BytesIO(b"%PDF-1.4 garbage"))
    assert not list((tmp_path / "att").rglob("*.pdf"))


def test_open_reads_back(store: LocalAttachmentStore):
    meta = store.put(CUSTOMER_A, SID, doc_type="delivery_note", seq=1, filename="dn.pdf", stream=BytesIO(SAMPLE))
    with store.open(CUSTOMER_A, meta) as f:
        assert f.read() == SAMPLE


def test_open_refuses_paths_outside_root(store: LocalAttachmentStore, tmp_path: Path):
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(SAMPLE)
    meta = AttachmentMeta(
        submission_id=SID, doc_type="x", seq=1, original_filename="s.pdf", storage_path=str(outside), sha256="a" * 64,
        size_bytes=1, page_count=1, has_text_layer=True, uploaded_at=__import__("datetime").datetime.now(__import__("datetime").UTC), uploaded_by="a@dist.com",
    )
    with pytest.raises(NotFoundError):
        store.open(CUSTOMER_A, meta)


def test_open_missing_file_is_not_found(store: LocalAttachmentStore):
    meta = store.put(CUSTOMER_A, SID, doc_type="delivery_note", seq=1, filename="dn.pdf", stream=BytesIO(SAMPLE))
    Path(meta.storage_path).unlink()
    with pytest.raises(NotFoundError):
        store.open(CUSTOMER_A, meta)
