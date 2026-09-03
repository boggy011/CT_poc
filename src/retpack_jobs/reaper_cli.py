"""Scheduled entry point for the attachment reaper. ``python -m retpack_jobs.reaper_cli [--dry-run]``."""

import logging
import os
import sys

from retpack_jobs.reaper import reap

logger = logging.getLogger(__name__)


def main(argv: list[str]) -> int:
    """Build the workspace container and reap orphans under the attachment Volume."""
    from retpack_adapters.factory import Settings, build_container

    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env(os.environ)
    if settings.backend not in ("delta", "lakebase"):
        print("reaper only runs against a workspace backend", file=sys.stderr)
        return 2
    container = build_container(settings)
    from databricks.sdk import WorkspaceClient

    from retpack_adapters.attachments.sdk_files import SdkFilesClient

    grace = int(os.environ.get("RETPACK_REAPER_GRACE_HOURS", "24"))
    result = reap(SdkFilesClient(WorkspaceClient()), container.ports.submissions, root=settings.volume_root, grace_hours=grace, dry_run="--dry-run" in argv)
    logger.info("scanned=%d referenced=%d deleted=%d skipped_recent=%d", result.scanned, result.referenced, len(result.deleted), result.skipped_recent)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
