from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from retpack_adapters.attachments.memory_files import InMemoryFilesClient
from retpack_adapters.attachments.volume import VolumeAttachmentStore
from retpack_adapters.mock.submissions import InMemorySubmissionRepository
from retpack_core import events
from retpack_core.attachments import load_attachment_policy
from retpack_core.ids import new_id
from retpack_jobs.reaper import reap
from tests.unit.conftest import CUSTOMER_A

ROOT = "/Volumes/c/s/att"
SAMPLE = Path("tests/fixtures/sample.pdf").read_bytes()


def test_reaper_deletes_only_old_unreferenced_objects(tmp_path: Path):
    files = InMemoryFilesClient()
    store = VolumeAttachmentStore(files, root=ROOT, policy=load_attachment_policy(Path("config/attachments.yaml")), spool_dir=tmp_path)
    repo = InMemorySubmissionRepository()

    sid = new_id()
    meta = store.put(CUSTOMER_A, sid, account_id="A1", doc_type="delivery_note", seq=1, filename="dn.pdf", stream=BytesIO(SAMPLE))
    repo.append_event(CUSTOMER_A, sid, 0, events.submitted(sid, "A1", actor=CUSTOMER_A.email, values={}, attachments=[meta]))

    old = datetime.now(UTC) - timedelta(days=3)
    files.objects[f"{ROOT}/A1/{new_id()}/other_1.pdf"] = (b"orphan-old", old)
    files.objects[f"{ROOT}/A1/{new_id()}/other_1.pdf"] = (b"orphan-new", datetime.now(UTC))
    files.objects[f"{ROOT}/A1/{sid}/other_9.pdf"] = (b"stray", old)  # same submission, not referenced

    dry = reap(files, repo, root=ROOT, grace_hours=24, dry_run=True)
    assert len(dry.deleted) == 2 and len(files.objects) == 4

    result = reap(files, repo, root=ROOT, grace_hours=24)
    assert result.scanned == 4 and result.referenced == 1 and result.skipped_recent == 1
    assert sorted(result.deleted) == sorted(p for p, (b, _) in {**files.objects, **{d: (b"", old) for d in result.deleted}}.items() if p not in files.objects)
    assert set(files.objects) == {meta.storage_path, next(p for p, (b, _) in files.objects.items() if b == b"orphan-new")}
