"""Delete Volume objects no submission references (orphans from failed submits). Plan step B12.

Runs as a scheduled Databricks Job with the SYSTEM principal. Anything younger
than ``grace_hours`` is left alone so an in-flight submit is never raced.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from retpack_adapters.attachments.files_client import FilesClient
from retpack_core.ports import SubmissionRepository
from retpack_core.principal import Principal, Role

logger = logging.getLogger(__name__)

SYSTEM = Principal(email="reaper@system.local", account_ids=frozenset(), role=Role.SYSTEM)
LISTING_LIMIT = 100_000


@dataclass(frozen=True)
class ReapResult:
    """Outcome of one run."""

    scanned: int
    referenced: int
    deleted: tuple[str, ...]
    skipped_recent: int


def referenced_paths(repo: SubmissionRepository) -> frozenset[str]:
    """Every ``storage_path`` referenced by any submission's attachments."""
    paths: set[str] = set()
    for sub in repo.list_submissions(SYSTEM, limit=LISTING_LIMIT):
        paths.update(m.storage_path for m in sub.attachments)
    return frozenset(paths)


def reap(files: FilesClient, repo: SubmissionRepository, *, root: str, grace_hours: int = 24, dry_run: bool = False) -> ReapResult:
    """Delete unreferenced objects under ``root`` older than ``grace_hours``."""
    cutoff = datetime.now(UTC) - timedelta(hours=grace_hours)
    known = referenced_paths(repo)
    deleted: list[str] = []
    scanned = skipped = 0
    for entry in files.list(root):
        scanned += 1
        if entry.path in known:
            continue
        if entry.modified_at > cutoff:
            skipped += 1
            continue
        logger.info("reaping orphan %s (%d bytes, modified %s)", entry.path, entry.size, entry.modified_at.isoformat())
        if not dry_run:
            files.delete(entry.path)
        deleted.append(entry.path)
    return ReapResult(scanned=scanned, referenced=len(known), deleted=tuple(deleted), skipped_recent=skipped)
