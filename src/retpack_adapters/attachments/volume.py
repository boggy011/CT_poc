"""Attachment store on a Unity Catalog Volume via a ``FilesClient``.

Bytes are spooled to a local temporary file (disk, not memory) so ``pypdf``
can inspect them and the SHA-256 is known before anything reaches the Volume.
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast

from retpack_adapters.attachments.common import check_segment, object_name, require_account, safe_filename
from retpack_adapters.attachments.files_client import FilesClient
from retpack_core.attachments import AttachmentPolicy
from retpack_core.errors import InvalidAttachmentError, NotFoundError
from retpack_core.models import AttachmentMeta
from retpack_core.pdf import copy_and_hash, inspect_pdf
from retpack_core.principal import Principal


class VolumeAttachmentStore:
    """Objects live at ``<root>/<account_id>/<submission_id>/<doc_type>_<seq>.pdf``."""

    def __init__(self, files: FilesClient, *, root: str, policy: AttachmentPolicy, spool_dir: Path | None = None) -> None:
        self._files = files
        self._root = root.rstrip("/")
        self._policy = policy
        self._spool = spool_dir
        if spool_dir is not None:
            spool_dir.mkdir(parents=True, exist_ok=True)

    def put(self, principal: Principal, submission_id: str, *, account_id: str, doc_type: str, seq: int, filename: str, stream: BinaryIO) -> AttachmentMeta:
        """See ``AttachmentStore.put``."""
        for segment in (account_id, submission_id, doc_type):
            check_segment(segment)
        require_account(principal, account_id)
        target = self._path(account_id, submission_id, doc_type, seq)
        with tempfile.NamedTemporaryFile(dir=self._spool, suffix=".pdf.part", delete=True) as handle:
            spool = cast(BinaryIO, handle)
            sha256, size = copy_and_hash(stream, spool, max_bytes=self._policy.max_size_bytes)
            spool.flush()
            info = inspect_pdf(Path(handle.name), timeout_s=self._policy.inspect_timeout_s)
            if info.page_count > self._policy.max_pages:
                raise InvalidAttachmentError(f"PDF has {info.page_count} pages; the limit is {self._policy.max_pages}")
            spool.seek(0)
            self._files.upload(target, spool)
        return AttachmentMeta(
            submission_id=submission_id,
            account_id=account_id,
            doc_type=doc_type,
            seq=seq,
            original_filename=safe_filename(filename),
            storage_path=target,
            sha256=sha256,
            size_bytes=size,
            page_count=info.page_count,
            has_text_layer=info.has_text_layer,
            uploaded_at=datetime.now(UTC),
            uploaded_by=principal.email,
        )

    def open(self, principal: Principal, meta: AttachmentMeta) -> BinaryIO:
        """See ``AttachmentStore.open``."""
        path = self._checked_path(principal, meta)
        try:
            return self._files.download(path)
        except FileNotFoundError:
            raise NotFoundError(f"attachment {meta.doc_type}/{meta.seq} not found") from None

    def delete(self, principal: Principal, meta: AttachmentMeta) -> None:
        """See ``AttachmentStore.delete``."""
        self._files.delete(self._checked_path(principal, meta))

    def _path(self, account_id: str, submission_id: str, doc_type: str, seq: int) -> str:
        return f"{self._root}/{account_id}/{submission_id}/{object_name(doc_type, seq)}"

    def _checked_path(self, principal: Principal, meta: AttachmentMeta) -> str:
        require_account(principal, meta.account_id)
        expected_prefix = f"{self._root}/{meta.account_id}/{meta.submission_id}/"
        if not meta.storage_path.startswith(expected_prefix) or "/../" in meta.storage_path:
            raise NotFoundError(f"attachment {meta.doc_type}/{meta.seq} not found")
        return meta.storage_path
