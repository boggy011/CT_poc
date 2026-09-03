"""Repository and store interfaces (Protocols) implemented by ``retpack_adapters``.

Every method on every port except the identity ports takes ``principal`` as its
first argument. ``tests/isolation`` enforces this structurally.
"""

from dataclasses import dataclass

from retpack_core.ports.attachment_store import AttachmentStore
from retpack_core.ports.identity import AccountDirectory, IdentityProvider
from retpack_core.ports.reference_repo import ReferenceRepository
from retpack_core.ports.submission_repo import SubmissionRepository


@dataclass(frozen=True)
class Ports:
    """The three data ports a service needs, bundled for injection."""

    submissions: SubmissionRepository
    reference: ReferenceRepository
    attachments: AttachmentStore


__all__ = ["AccountDirectory", "AttachmentStore", "IdentityProvider", "Ports", "ReferenceRepository", "SubmissionRepository"]
