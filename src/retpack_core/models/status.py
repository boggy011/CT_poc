"""Submission status.

PLACEHOLDER. The real enum is ABI input 3 (see RETPACK_REQUIREMENTS.md section 7)
and must be frozen in the data contract before the AI team builds against it.
Keep every member in this one file so the rename is a single commit.
"""

from enum import StrEnum


class Status(StrEnum):
    """Derived submission status (never stored; folded from events)."""

    SUBMITTED = "SUBMITTED"
    VALIDATED = "VALIDATED"
    CPI_PENDING = "CPI_PENDING"
    CPI_DONE = "CPI_DONE"
    CPI_FAILED = "CPI_FAILED"
