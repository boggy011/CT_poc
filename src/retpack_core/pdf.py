"""PDF byte handling: magic-byte check, streaming hash, sandboxed structure inspection.

Pure Python plus ``pypdf``; shared by every attachment store. Inspection runs in
a child process with a wall-clock timeout and an address-space limit because
``pypdf`` has no bound on the work a small hostile file can trigger, and the app
is a single shared container (req. 5.4).
"""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from retpack_core.errors import InvalidAttachmentError

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
DEFAULT_CHUNK = 1024 * 1024
DEFAULT_INSPECT_TIMEOUT_S = 15.0
DEFAULT_INSPECT_MEMORY_MB = 768


@dataclass(frozen=True)
class PdfInfo:
    """Cheap upload-time facts about a PDF."""

    page_count: int
    has_text_layer: bool


def copy_and_hash(src: BinaryIO, dst: BinaryIO, *, max_bytes: int, chunk_size: int = DEFAULT_CHUNK) -> tuple[str, int]:
    """Stream ``src`` into ``dst`` while hashing, enforcing the PDF header and a size cap.

    The ``%PDF-`` header must be at offset 0: anything else (HTML or ZIP
    polyglots with the header further in) is rejected. Never holds more than
    one chunk in memory.

    Returns:
        ``(sha256_hex, size_bytes)``.

    Raises:
        InvalidAttachmentError: If empty, not a PDF, or larger than ``max_bytes``.
    """
    import hashlib

    head = _read_at_least(src, len(PDF_MAGIC), chunk_size)
    if not head:
        raise InvalidAttachmentError("empty file")
    if not head.startswith(PDF_MAGIC):
        raise InvalidAttachmentError("not a PDF (file must start with %PDF-)")
    digest = hashlib.sha256()
    size = 0
    chunk = head
    while chunk:
        size += len(chunk)
        if size > max_bytes:
            raise InvalidAttachmentError(f"file exceeds the {max_bytes // (1024 * 1024)} MB limit")
        digest.update(chunk)
        dst.write(chunk)
        chunk = src.read(chunk_size)
    return digest.hexdigest(), size


def _read_at_least(src: BinaryIO, n: int, chunk_size: int) -> bytes:
    buf = b""
    while len(buf) < n:
        more = src.read(chunk_size)
        if not more:
            break
        buf += more
    return buf


def inspect_pdf(path: Path, *, timeout_s: float = DEFAULT_INSPECT_TIMEOUT_S, memory_mb: int = DEFAULT_INSPECT_MEMORY_MB) -> PdfInfo:
    """Count pages and detect a text layer, in a sandboxed child process.

    Args:
        path: Stored file to inspect.
        timeout_s: Wall-clock budget; exceeding it rejects the file.
        memory_mb: Address-space limit for the child (best effort per platform).

    Raises:
        InvalidAttachmentError: If the file cannot be parsed, or inspection
            exceeds the time or memory budget.
    """
    cmd = [sys.executable, "-m", "retpack_core.pdf_inspect", str(path), str(memory_mb)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        raise InvalidAttachmentError(f"PDF could not be inspected within {timeout_s:.0f} seconds") from None
    outcome = _parse_outcome(proc.stdout, proc.returncode, proc.stderr)
    if not outcome.get("ok"):
        logger.warning("PDF inspection rejected %s: %s", path.name, outcome.get("error"))
        raise InvalidAttachmentError("unreadable PDF")
    return PdfInfo(page_count=int(outcome["page_count"]), has_text_layer=bool(outcome["has_text_layer"]))


def _parse_outcome(stdout: str, returncode: int, stderr: str) -> dict[str, Any]:
    try:
        data = json.loads(stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "error": f"inspection process exited with {returncode} (memory limit?): {stderr[-300:]}"}
    return dict(data) if isinstance(data, dict) else {"ok": False, "error": "malformed inspection output"}
