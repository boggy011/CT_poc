"""Scheduled entry point: ``python -m retpack_jobs.cpi_dispatch_cli``. Runs every few minutes, one run at a time."""

import logging
import os
import sys

from retpack_jobs.cpi_dispatch import run_once
from retpack_jobs.cpi_http import HttpCpiClient

logger = logging.getLogger(__name__)


def main() -> int:
    """Dispatch pending validated requests through CPI."""
    from retpack_adapters.factory import Settings, build_container

    logging.basicConfig(level=logging.INFO)
    url = os.environ.get("RETPACK_CPI_URL", "")
    token = os.environ.get("RETPACK_CPI_TOKEN", "")
    if not url or not token:
        print("RETPACK_CPI_URL and RETPACK_CPI_TOKEN are required (ABI input 5)", file=sys.stderr)
        return 2
    container = build_container(Settings.from_env(os.environ))
    report = run_once(container.ports.submissions, HttpCpiClient(url, bearer_token=token))
    logger.info(
        "succeeded=%d retried=%d dead_lettered=%d skipped=%d", len(report.succeeded), len(report.retried), len(report.dead_lettered), len(report.skipped)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
