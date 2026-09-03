"""Opaque PDF storage (local dir in mock, Unity Catalog Volume otherwise)."""

from typing import BinaryIO, Protocol

from retpack_core.models import AttachmentMeta
from retpack_core.principal import Principal


class AttachmentStore(Protocol):
    """Streams PDF bytes to storage and returns typed metadata.

    Access control for reads is enforced by the calling service through the
    submission repository (a principal can only obtain ``AttachmentMeta`` for
    submissions it may see). The store records ``principal`` for audit.
    """

    def put(self, principal: Principal, submission_id: str, *, doc_type: str, seq: int, filename: str, stream: BinaryIO) -> AttachmentMeta:
        """Validate and store one PDF.

        The stream is consumed once and never buffered wholesale in memory.

        Raises:
            InvalidAttachmentError: If the bytes are not a PDF or exceed the size limit.
        """
        ...

    def open(self, principal: Principal, meta: AttachmentMeta) -> BinaryIO:
        """Open the stored bytes for reading (caller closes)."""
        ...
