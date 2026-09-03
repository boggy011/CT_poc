"""Pieces shared by every attachment store."""

import re
from pathlib import PurePosixPath, PureWindowsPath

from retpack_core.errors import NotFoundError
from retpack_core.principal import Principal

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_\-]+$")
_UNSAFE_FILENAME_CHARS = re.compile(r'[\x00-\x1f\x7f"\\/]')
MAX_FILENAME = 255


def safe_filename(filename: str) -> str:
    """Strip directories, control characters and quotes; cap the length; never empty."""
    name = PurePosixPath(PureWindowsPath(filename).name).name
    name = _UNSAFE_FILENAME_CHARS.sub("_", name).strip(" .")
    if not name:
        name = "document.pdf"
    return name[:MAX_FILENAME]


def check_segment(value: str) -> None:
    """Reject anything that is not a plain path segment.

    Raises:
        ValueError: On separators, dots, or other unexpected characters.
    """
    if not _SAFE_SEGMENT.match(value):
        raise ValueError(f"unsafe path segment {value!r}")


def require_account(principal: Principal, account_id: str) -> None:
    """Second isolation layer: a scoped principal may only touch its own accounts.

    Raises:
        NotFoundError: Never a distinct forbidden error (no existence leak).
    """
    if principal.is_scoped and account_id not in principal.account_ids:
        raise NotFoundError("attachment not found")


def object_name(doc_type: str, seq: int) -> str:
    """Stored object name for one attachment."""
    return f"{doc_type}_{seq}.pdf"
