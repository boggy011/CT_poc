"""Tiny test doubles that are not worth a real adapter."""

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from typing import BinaryIO

from retpack_core.models import AttachmentMeta
from retpack_core.principal import Principal


class RecordingAttachmentStore:
    """Keeps bytes in a dict; good enough for service tests."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.puts: list[tuple[str, str, str]] = []

    def put(self, principal: Principal, submission_id: str, *, doc_type: str, seq: int, filename: str, stream: BinaryIO) -> AttachmentMeta:
        data = stream.read()
        path = f"mem://{submission_id}/{doc_type}_{seq}.pdf"
        self.blobs[path] = data
        self.puts.append((principal.email, submission_id, doc_type))
        return AttachmentMeta(
            submission_id=submission_id,
            doc_type=doc_type,
            seq=seq,
            original_filename=filename,
            storage_path=path,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            page_count=1,
            has_text_layer=not data.startswith(b"%PDF-SCAN"),
            uploaded_at=datetime.now(UTC),
            uploaded_by=principal.email,
        )

    def open(self, principal: Principal, meta: AttachmentMeta) -> BinaryIO:
        return BytesIO(self.blobs[meta.storage_path])
