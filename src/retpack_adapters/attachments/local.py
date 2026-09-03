"""Attachment store on a local directory. Used by the mock backend and by tests."""

from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from retpack_adapters.attachments.common import check_segment, object_name, require_account, safe_filename
from retpack_core.attachments import AttachmentPolicy
from retpack_core.errors import InvalidAttachmentError, NotFoundError
from retpack_core.models import AttachmentMeta
from retpack_core.pdf import copy_and_hash, inspect_pdf
from retpack_core.principal import Principal


class LocalAttachmentStore:
    """Writes ``<root>/<account_id>/<submission_id>/<doc_type>_<seq>.pdf`` via a ``.part`` file."""

    def __init__(self, root: Path, *, policy: AttachmentPolicy) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._policy = policy

    def put(self, principal: Principal, submission_id: str, *, account_id: str, doc_type: str, seq: int, filename: str, stream: BinaryIO) -> AttachmentMeta:
        """See ``AttachmentStore.put``."""
        for segment in (account_id, submission_id, doc_type):
            check_segment(segment)
        require_account(principal, account_id)
        target_dir = self._root / account_id / submission_id
        target_dir.mkdir(parents=True, exist_ok=True)
        final = target_dir / object_name(doc_type, seq)
        part = final.with_name(final.name + ".part")
        try:
            with part.open("wb") as dst:
                sha256, size = copy_and_hash(stream, dst, max_bytes=self._policy.max_size_bytes)
            info = inspect_pdf(part, timeout_s=self._policy.inspect_timeout_s)
            if info.page_count > self._policy.max_pages:
                raise InvalidAttachmentError(f"PDF has {info.page_count} pages; the limit is {self._policy.max_pages}")
            part.replace(final)
        except BaseException:
            part.unlink(missing_ok=True)
            _prune_empty(target_dir, self._root)
            raise
        return AttachmentMeta(
            submission_id=submission_id,
            account_id=account_id,
            doc_type=doc_type,
            seq=seq,
            original_filename=safe_filename(filename),
            storage_path=str(final),
            sha256=sha256,
            size_bytes=size,
            page_count=info.page_count,
            has_text_layer=info.has_text_layer,
            uploaded_at=datetime.now(UTC),
            uploaded_by=principal.email,
        )

    def open(self, principal: Principal, meta: AttachmentMeta) -> BinaryIO:
        """See ``AttachmentStore.open``. Enforces account scope and store-root containment."""
        path = self._resolve(principal, meta)
        if not path.is_file():
            raise NotFoundError(f"attachment {meta.doc_type}/{meta.seq} not found")
        return path.open("rb")

    def delete(self, principal: Principal, meta: AttachmentMeta) -> None:
        """See ``AttachmentStore.delete``."""
        path = self._resolve(principal, meta)
        path.unlink(missing_ok=True)
        _prune_empty(path.parent, self._root)

    def _resolve(self, principal: Principal, meta: AttachmentMeta) -> Path:
        require_account(principal, meta.account_id)
        path = Path(meta.storage_path).resolve()
        expected_dir = (self._root / meta.account_id / meta.submission_id).resolve()
        if not path.is_relative_to(expected_dir):
            raise NotFoundError(f"attachment {meta.doc_type}/{meta.seq} not found")
        return path


def _prune_empty(path: Path, stop: Path) -> None:
    stop = stop.resolve()
    current = path.resolve()
    while current != stop and current.is_relative_to(stop):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
