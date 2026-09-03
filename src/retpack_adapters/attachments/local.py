"""Attachment store on a local directory. Used by the mock backend and by tests."""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from retpack_core.errors import InvalidAttachmentError, NotFoundError
from retpack_core.models import AttachmentMeta
from retpack_core.pdf import copy_and_hash, inspect_pdf
from retpack_core.principal import Principal

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_\-]+$")


class LocalAttachmentStore:
    """Writes ``<root>/<submission_id>/<doc_type>_<seq>.pdf`` via a ``.part`` file."""

    def __init__(self, root: Path, *, max_bytes: int) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes

    def put(self, principal: Principal, submission_id: str, *, doc_type: str, seq: int, filename: str, stream: BinaryIO) -> AttachmentMeta:
        """See ``AttachmentStore.put``."""
        _check_segment(submission_id)
        _check_segment(doc_type)
        target_dir = self._root / submission_id
        target_dir.mkdir(parents=True, exist_ok=True)
        final = target_dir / f"{doc_type}_{seq}.pdf"
        part = final.with_name(final.name + ".part")
        try:
            with part.open("wb") as dst:
                sha256, size = copy_and_hash(stream, dst, max_bytes=self._max_bytes)
            with part.open("rb") as src:
                info = inspect_pdf(src)
        except InvalidAttachmentError:
            part.unlink(missing_ok=True)
            _rmdir_if_empty(target_dir)
            raise
        part.replace(final)
        return AttachmentMeta(
            submission_id=submission_id,
            doc_type=doc_type,
            seq=seq,
            original_filename=filename,
            storage_path=str(final),
            sha256=sha256,
            size_bytes=size,
            page_count=info.page_count,
            has_text_layer=info.has_text_layer,
            uploaded_at=datetime.now(UTC),
            uploaded_by=principal.email,
        )

    def open(self, principal: Principal, meta: AttachmentMeta) -> BinaryIO:
        """See ``AttachmentStore.open``. Refuses paths outside the store root."""
        path = Path(meta.storage_path).resolve()
        if not path.is_relative_to(self._root.resolve()) or not path.is_file():
            raise NotFoundError(f"attachment {meta.doc_type}/{meta.seq} not found")
        return path.open("rb")


def _check_segment(value: str) -> None:
    if not _SAFE_SEGMENT.match(value):
        raise ValueError(f"unsafe path segment {value!r}")


def _rmdir_if_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass
