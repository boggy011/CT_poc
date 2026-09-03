"""PDF byte handling: magic-byte check, streaming hash, cheap structure inspection.

Pure Python plus ``pypdf``; shared by every attachment store.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from pypdf import PdfReader

from retpack_core.errors import InvalidAttachmentError

PDF_MAGIC = b"%PDF-"
MAGIC_WINDOW = 1024
"""The PDF header must appear within the first 1024 bytes (PDF 1.7 spec, appendix H)."""
TEXT_LAYER_PAGES = 3
"""How many pages to sample when deciding whether a PDF has extractable text."""
DEFAULT_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class PdfInfo:
    """Cheap upload-time facts about a PDF."""

    page_count: int
    has_text_layer: bool


def copy_and_hash(src: BinaryIO, dst: BinaryIO, *, max_bytes: int, chunk_size: int = DEFAULT_CHUNK) -> tuple[str, int]:
    """Stream ``src`` into ``dst`` while hashing, enforcing PDF magic and a size cap.

    Never holds more than one chunk in memory.

    Returns:
        ``(sha256_hex, size_bytes)``.

    Raises:
        InvalidAttachmentError: If empty, not a PDF, or larger than ``max_bytes``.
    """
    digest = hashlib.sha256()
    size = 0
    first = True
    while chunk := src.read(chunk_size):
        if first:
            if PDF_MAGIC not in chunk[:MAGIC_WINDOW]:
                raise InvalidAttachmentError("not a PDF (missing %PDF- header)")
            first = False
        size += len(chunk)
        if size > max_bytes:
            raise InvalidAttachmentError(f"file exceeds the {max_bytes // (1024 * 1024)} MB limit")
        digest.update(chunk)
        dst.write(chunk)
    if first:
        raise InvalidAttachmentError("empty file")
    return digest.hexdigest(), size


def inspect_pdf(source: BinaryIO | Path) -> PdfInfo:
    """Count pages and detect whether the first pages carry extractable text.

    Raises:
        InvalidAttachmentError: If ``pypdf`` cannot parse the file.
    """
    try:
        reader = PdfReader(source)
        page_count = len(reader.pages)
        has_text = any(page.extract_text().strip() for page in reader.pages[:TEXT_LAYER_PAGES])
    except Exception as exc:  # pypdf raises a wide family of errors
        raise InvalidAttachmentError(f"unreadable PDF: {exc}") from exc
    return PdfInfo(page_count=page_count, has_text_layer=has_text)
