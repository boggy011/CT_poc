"""External intake: validate, store PDFs, append one SUBMITTED event."""

import hashlib
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, BinaryIO

from retpack_core import events
from retpack_core.attachments import AttachmentPolicy
from retpack_core.audit import audit
from retpack_core.errors import NotPermittedError, ValidationFailedError
from retpack_core.fieldspec import FormSpec, validate_values
from retpack_core.fold import Submission, fold
from retpack_core.ids import new_id
from retpack_core.models import AttachmentMeta
from retpack_core.pdf import PDF_MAGIC
from retpack_core.ports import Ports
from retpack_core.principal import Principal
from retpack_core.services.options import Choice, enum_choices, enum_options

logger = logging.getLogger(__name__)
_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class UploadedPdf:
    """One file from the intake form, not yet validated or stored."""

    doc_type: str
    filename: str
    stream: BinaryIO


@dataclass(frozen=True)
class IntakeResult:
    """What the UI renders after submit. Built from the event just appended, never re-read."""

    submission: Submission
    warnings: tuple[str, ...] = ()


class IntakeService:
    """Customer-facing submission (FR-03, FR-04, FR-05)."""

    def __init__(self, ports: Ports, spec: FormSpec, policy: AttachmentPolicy) -> None:
        self._ports = ports
        self._spec = spec
        self._policy = policy

    def enum_choices(self, principal: Principal, *, account_id: str | None) -> dict[str, tuple[Choice, ...]]:
        """Labelled dropdown options for the renderer."""
        return enum_choices(self._ports.reference, self._spec, principal, account_id=account_id)

    def enum_options(self, principal: Principal, *, account_id: str | None) -> dict[str, tuple[str, ...]]:
        """Allowed values per enum field, as the validator expects."""
        return enum_options(self._ports.reference, self._spec, principal, account_id=account_id)

    def submit(self, principal: Principal, values: Mapping[str, Any], attachments: Sequence[UploadedPdf]) -> IntakeResult:
        """Validate and persist a new request as exactly one event append.

        Raises:
            NotPermittedError: If the principal is not a customer, or the
                submitted account is not one of theirs.
            ValidationFailedError: On any field or attachment rule violation;
                nothing is stored in that case.
        """
        if not principal.is_scoped:
            audit("submit_denied", principal, reason="not_customer")
            raise NotPermittedError("only customer accounts can submit requests")
        account_id = self._account_from(values)
        result = validate_values(values, self._spec, enum_options=self.enum_options(principal, account_id=account_id))
        errors = dict(result.errors)
        errors.update(self._check_attachments(attachments))
        if errors:
            raise ValidationFailedError(errors)
        account_id = self._owned_account(principal, result.values)

        submission_id = new_id()
        metas: list[AttachmentMeta] = []
        try:
            for i, upload in enumerate(attachments, start=1):
                metas.append(self._store(principal, submission_id, account_id, i, upload))
            event = events.submitted(submission_id, account_id, actor=principal.email, values=result.values, attachments=metas)
            self._ports.submissions.append_event(principal, submission_id, 0, event)
        except Exception:
            self._discard(principal, metas)
            raise
        audit("submission_created", principal, submission_id=submission_id, account_id=account_id, attachments=len(metas))
        return IntakeResult(submission=fold([event]), warnings=_warnings(metas))

    def _account_from(self, values: Mapping[str, Any]) -> str | None:
        f = self._spec.account_field
        raw = values.get(f.name) if f else None
        return str(raw) if raw else None

    def _owned_account(self, principal: Principal, cleaned: Mapping[str, Any]) -> str:
        """The account the request belongs to. Enforced here, independent of the field spec."""
        f = self._spec.account_field
        account = cleaned.get(f.name) if f else None
        if account is None or str(account) not in principal.account_ids:
            audit("submit_denied", principal, reason="foreign_account", account_id=account)
            raise NotPermittedError("the request must belong to one of your accounts")
        return str(account)

    def _store(self, principal: Principal, submission_id: str, account_id: str, seq: int, upload: UploadedPdf) -> AttachmentMeta:
        return self._ports.attachments.put(
            principal, submission_id, account_id=account_id, doc_type=upload.doc_type, seq=seq, filename=upload.filename, stream=upload.stream
        )

    def _discard(self, principal: Principal, metas: Sequence[AttachmentMeta]) -> None:
        for meta in metas:
            try:
                self._ports.attachments.delete(principal, meta)
            except Exception:  # best effort; the original error is what matters
                logger.exception("could not remove attachment %s after failed submit", meta.storage_path)

    def _check_attachments(self, attachments: Sequence[UploadedPdf]) -> dict[str, list[str]]:
        counts: dict[str, int] = {}
        for a in attachments:
            counts[a.doc_type] = counts.get(a.doc_type, 0) + 1
        errors = {f"attachments.{name}": [msg] for name, msg in self._policy.check_counts(counts).items()}
        digests = []
        for a in attachments:
            digest, is_pdf = _sha256_and_magic(a.stream)
            if not is_pdf:
                audit("attachment_rejected", None, reason="not_pdf", doc_type=a.doc_type)
                errors[f"attachments.{a.doc_type}"] = [f"{a.filename} is not a PDF"]
            digests.append(digest)
        if len(set(digests)) != len(digests):
            errors["attachments"] = ["the same PDF was attached more than once"]
        return errors


def _sha256_and_magic(stream: BinaryIO) -> tuple[str, bool]:
    h = hashlib.sha256()
    first = True
    is_pdf = False
    for chunk in iter(lambda: stream.read(_CHUNK), b""):
        if first:
            is_pdf = chunk.startswith(PDF_MAGIC)
            first = False
        h.update(chunk)
    stream.seek(0)
    return h.hexdigest(), is_pdf


def _warnings(metas: Sequence[AttachmentMeta]) -> tuple[str, ...]:
    return tuple(f"{m.original_filename} has no text layer; the automated cross-check cannot read it" for m in metas if not m.has_text_layer)
