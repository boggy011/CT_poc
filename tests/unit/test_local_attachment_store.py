from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest

from retpack_adapters.attachments.local import LocalAttachmentStore, safe_filename
from retpack_core.attachments import parse_attachment_policy
from retpack_core.errors import InvalidAttachmentError, NotFoundError
from retpack_core.models import AttachmentMeta
from tests.unit.conftest import CUSTOMER_A, CUSTOMER_B, INTERNAL

SAMPLE = Path("tests/fixtures/sample.pdf").read_bytes()
SCANNED = Path("tests/fixtures/scanned.pdf").read_bytes()
SID = "0190f0a0-0000-7000-8000-000000000001"


def policy(**overrides):
    base = {
        "version": 1,
        "max_size_mb": 1,
        "max_pages": 10,
        "inspect_timeout_s": 15,
        "doc_types": [{"name": "delivery_note", "label": "DN"}, {"name": "other", "label": "O"}],
    }
    return parse_attachment_policy({**base, **overrides})


@pytest.fixture
def store(tmp_path: Path) -> LocalAttachmentStore:
    return LocalAttachmentStore(tmp_path / "att", policy=policy())


def test_put_stores_under_account_and_submission(store: LocalAttachmentStore, tmp_path: Path):
    meta = store.put(CUSTOMER_A, SID, account_id="A1", doc_type="delivery_note", seq=1, filename="../evil/dn.pdf", stream=BytesIO(SAMPLE))
    assert meta.account_id == "A1"
    assert meta.original_filename == "dn.pdf"
    assert meta.page_count == 1 and meta.has_text_layer is True
    assert meta.size_bytes == len(SAMPLE)
    stored = Path(meta.storage_path)
    assert stored == tmp_path / "att" / "A1" / SID / "delivery_note_1.pdf"
    assert stored.read_bytes() == SAMPLE
    assert not list(stored.parent.glob("*.part"))


def test_put_for_foreign_account_is_not_found(store: LocalAttachmentStore, tmp_path: Path):
    with pytest.raises(NotFoundError):
        store.put(CUSTOMER_B, SID, account_id="A1", doc_type="other", seq=1, filename="x.pdf", stream=BytesIO(SAMPLE))
    assert not list((tmp_path / "att").rglob("*"))


def test_put_scanned_sets_flag(store: LocalAttachmentStore):
    meta = store.put(CUSTOMER_A, SID, account_id="A1", doc_type="other", seq=2, filename="scan.pdf", stream=BytesIO(SCANNED))
    assert meta.has_text_layer is False


@pytest.mark.parametrize("body", [b"not a pdf", b"%PDF-1.4 garbage"])
def test_put_rejects_bad_bytes_and_leaves_nothing_behind(store: LocalAttachmentStore, tmp_path: Path, body: bytes):
    with pytest.raises(InvalidAttachmentError):
        store.put(CUSTOMER_A, SID, account_id="A1", doc_type="other", seq=1, filename="x.pdf", stream=BytesIO(body))
    assert not list((tmp_path / "att").rglob("*"))


def test_put_rejects_too_many_pages(tmp_path: Path):
    store = LocalAttachmentStore(tmp_path / "att", policy=policy(max_pages=0) if False else policy())
    strict = LocalAttachmentStore(tmp_path / "strict", policy=parse_attachment_policy({**policy().model_dump(), "max_pages": 1}))
    strict.put(CUSTOMER_A, SID, account_id="A1", doc_type="other", seq=1, filename="one.pdf", stream=BytesIO(SAMPLE))
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=10, height=10)
    w.add_blank_page(width=10, height=10)
    buf = BytesIO()
    w.write(buf)
    with pytest.raises(InvalidAttachmentError, match="pages"):
        strict.put(CUSTOMER_A, SID, account_id="A1", doc_type="other", seq=2, filename="two.pdf", stream=BytesIO(buf.getvalue()))
    assert store is not None


def test_open_reads_back_and_internal_may_open(store: LocalAttachmentStore):
    meta = store.put(CUSTOMER_A, SID, account_id="A1", doc_type="delivery_note", seq=1, filename="dn.pdf", stream=BytesIO(SAMPLE))
    with store.open(CUSTOMER_A, meta) as f:
        assert f.read() == SAMPLE
    with store.open(INTERNAL, meta) as f:
        assert f.read() == SAMPLE


def test_open_by_other_tenant_is_not_found(store: LocalAttachmentStore):
    meta = store.put(CUSTOMER_A, SID, account_id="A1", doc_type="delivery_note", seq=1, filename="dn.pdf", stream=BytesIO(SAMPLE))
    with pytest.raises(NotFoundError):
        store.open(CUSTOMER_B, meta)
    with pytest.raises(NotFoundError):
        store.delete(CUSTOMER_B, meta)


def _meta(path: Path, account: str = "A1") -> AttachmentMeta:
    return AttachmentMeta(
        submission_id=SID,
        account_id=account,
        doc_type="x",
        seq=1,
        original_filename="s.pdf",
        storage_path=str(path),
        sha256="a" * 64,
        size_bytes=1,
        page_count=1,
        has_text_layer=True,
        uploaded_at=datetime.now(UTC),
        uploaded_by="a@dist.com",
    )


def test_open_refuses_paths_outside_the_submission_directory(store: LocalAttachmentStore, tmp_path: Path):
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(SAMPLE)
    with pytest.raises(NotFoundError):
        store.open(CUSTOMER_A, _meta(outside))
    other_dir = tmp_path / "att" / "A1" / "0190f0a0-0000-7000-8000-000000000002" / "x_1.pdf"
    other_dir.parent.mkdir(parents=True)
    other_dir.write_bytes(SAMPLE)
    with pytest.raises(NotFoundError):
        store.open(CUSTOMER_A, _meta(other_dir))


def test_open_missing_file_is_not_found(store: LocalAttachmentStore):
    meta = store.put(CUSTOMER_A, SID, account_id="A1", doc_type="delivery_note", seq=1, filename="dn.pdf", stream=BytesIO(SAMPLE))
    Path(meta.storage_path).unlink()
    with pytest.raises(NotFoundError):
        store.open(CUSTOMER_A, meta)


def test_delete_removes_file_and_empty_directories(store: LocalAttachmentStore, tmp_path: Path):
    meta = store.put(CUSTOMER_A, SID, account_id="A1", doc_type="delivery_note", seq=1, filename="dn.pdf", stream=BytesIO(SAMPLE))
    store.delete(CUSTOMER_A, meta)
    assert not list((tmp_path / "att").rglob("*"))
    store.delete(CUSTOMER_A, meta)  # idempotent


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("dn.pdf", "dn.pdf"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\x\\note.pdf", "note.pdf"),
        ('a"b.pdf', "a_b.pdf"),
        ("evil\r\nContent-Type: text.pdf", "evil__Content-Type: text.pdf"),
        ("dir/sub/html.pdf", "html.pdf"),
        ("", "document.pdf"),
        ("...", "document.pdf"),
        ("x" * 300 + ".pdf", "x" * 255),
    ],
)
def test_safe_filename(raw: str, expected: str):
    assert safe_filename(raw) == expected
