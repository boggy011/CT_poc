from io import BytesIO
from pathlib import Path

import pytest

from retpack_adapters.attachments.memory_files import InMemoryFilesClient
from retpack_adapters.attachments.volume import VolumeAttachmentStore
from retpack_core.attachments import load_attachment_policy
from retpack_core.errors import InvalidAttachmentError, NotFoundError
from tests.unit.conftest import CUSTOMER_A, CUSTOMER_B

SAMPLE = Path("tests/fixtures/sample.pdf").read_bytes()
SID = "0190f0a0-0000-7000-8000-000000000001"
ROOT = "/Volumes/cat/retpack/attachments"


@pytest.fixture
def files() -> InMemoryFilesClient:
    return InMemoryFilesClient()


@pytest.fixture
def store(files: InMemoryFilesClient, tmp_path: Path) -> VolumeAttachmentStore:
    return VolumeAttachmentStore(files, root=ROOT, policy=load_attachment_policy(Path("config/attachments.yaml")), spool_dir=tmp_path)


def test_put_uploads_under_account_prefix_and_leaves_no_spool(store: VolumeAttachmentStore, files: InMemoryFilesClient, tmp_path: Path):
    meta = store.put(CUSTOMER_A, SID, account_id="A1", doc_type="delivery_note", seq=1, filename="dn.pdf", stream=BytesIO(SAMPLE))
    assert meta.storage_path == f"{ROOT}/A1/{SID}/delivery_note_1.pdf"
    assert files.objects[meta.storage_path][0] == SAMPLE
    assert meta.has_text_layer and meta.page_count == 1
    assert not list(tmp_path.iterdir())


def test_rejected_bytes_never_reach_the_volume(store: VolumeAttachmentStore, files: InMemoryFilesClient):
    with pytest.raises(InvalidAttachmentError):
        store.put(CUSTOMER_A, SID, account_id="A1", doc_type="other", seq=1, filename="x.pdf", stream=BytesIO(b"%PDF-1.4 garbage"))
    assert files.objects == {}


def test_open_delete_and_scope(store: VolumeAttachmentStore, files: InMemoryFilesClient):
    meta = store.put(CUSTOMER_A, SID, account_id="A1", doc_type="delivery_note", seq=1, filename="dn.pdf", stream=BytesIO(SAMPLE))
    with store.open(CUSTOMER_A, meta) as f:
        assert f.read() == SAMPLE
    with pytest.raises(NotFoundError):
        store.open(CUSTOMER_B, meta)
    forged = meta.model_copy(update={"storage_path": f"{ROOT}/B1/{SID}/delivery_note_1.pdf"})
    with pytest.raises(NotFoundError):
        store.open(CUSTOMER_A, forged)
    store.delete(CUSTOMER_A, meta)
    assert files.objects == {}
    with pytest.raises(NotFoundError):
        store.open(CUSTOMER_A, meta)


def test_list_prefix(files: InMemoryFilesClient):
    files.upload(f"{ROOT}/A1/x/a.pdf", BytesIO(b"1"))
    files.upload(f"{ROOT}/B1/y/b.pdf", BytesIO(b"22"))
    files.upload("/Volumes/other/z.pdf", BytesIO(b"3"))
    assert {e.path for e in files.list(ROOT)} == {f"{ROOT}/A1/x/a.pdf", f"{ROOT}/B1/y/b.pdf"}
    assert {e.path for e in files.list(f"{ROOT}/A1")} == {f"{ROOT}/A1/x/a.pdf"}
