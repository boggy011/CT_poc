"""Opaque PDF storage (local dir in mock, Unity Catalog Volume otherwise)."""

from typing import BinaryIO, Protocol

from retpack_core.models import AttachmentMeta
from retpack_core.principal import Principal


class AttachmentStore(Protocol):
    """Streams PDF bytes to storage and returns typed metadata.

    Objects live under ``<account_id>/<submission_id>/`` so the store can
    enforce account scope on its own (second isolation layer for FR-02),
    independently of the service-level check through the submission repository.
    """

    def put(self, principal: Principal, submission_id: str, *, account_id: str, doc_type: str, seq: int, filename: str, stream: BinaryIO) -> AttachmentMeta:
        """Validate and store one PDF.

        The stream is consumed once and never buffered wholesale in memory.

        Raises:
            InvalidAttachmentError: If the bytes are not a PDF, exceed the size
                limit, or cannot be inspected within budget.
            NotFoundError: If ``account_id`` is outside the principal's scope.
        """
        ...

    def open(self, principal: Principal, meta: AttachmentMeta) -> BinaryIO:
        """Open the stored bytes for reading (caller closes).

        Raises:
            NotFoundError: If the object is missing or outside the principal's scope.
        """
        ...

    def delete(self, principal: Principal, meta: AttachmentMeta) -> None:
        """Remove one stored object; missing objects are ignored.

        Raises:
            NotFoundError: If outside the principal's scope.
        """
        ...
