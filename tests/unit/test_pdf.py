from io import BytesIO
from pathlib import Path

import pytest

from retpack_core.errors import InvalidAttachmentError
from retpack_core.pdf import copy_and_hash, inspect_pdf

SAMPLE = Path("tests/fixtures/sample.pdf").read_bytes()
SCANNED = Path("tests/fixtures/scanned.pdf").read_bytes()


def test_copy_and_hash_streams_and_hashes():
    import hashlib

    dst = BytesIO()
    sha, size = copy_and_hash(BytesIO(SAMPLE), dst, max_bytes=1_000_000, chunk_size=7)
    assert dst.getvalue() == SAMPLE
    assert size == len(SAMPLE)
    assert sha == hashlib.sha256(SAMPLE).hexdigest()


def test_rejects_non_pdf_by_magic_bytes_not_extension():
    with pytest.raises(InvalidAttachmentError, match="not a PDF"):
        copy_and_hash(BytesIO(b"GIF89a....."), BytesIO(), max_bytes=1000)


def test_accepts_magic_within_first_kilobyte():
    dst = BytesIO()
    copy_and_hash(BytesIO(b"\n" * 100 + b"%PDF-1.4 rest"), dst, max_bytes=1000)
    assert dst.getvalue().endswith(b"rest")


def test_rejects_empty():
    with pytest.raises(InvalidAttachmentError, match="empty"):
        copy_and_hash(BytesIO(b""), BytesIO(), max_bytes=1000)


def test_rejects_oversize_before_reading_everything():
    class Counting(BytesIO):
        reads = 0

        def read(self, n: int = -1) -> bytes:
            self.reads += 1
            return super().read(n)

    src = Counting(b"%PDF-" + b"x" * 5000)
    with pytest.raises(InvalidAttachmentError, match="exceeds"):
        copy_and_hash(src, BytesIO(), max_bytes=1000, chunk_size=100)
    assert src.reads < 20


def test_inspect_text_pdf():
    info = inspect_pdf(BytesIO(SAMPLE))
    assert info.page_count == 1
    assert info.has_text_layer is True


def test_inspect_scanned_pdf():
    info = inspect_pdf(BytesIO(SCANNED))
    assert info.page_count == 1
    assert info.has_text_layer is False


def test_inspect_corrupt_pdf():
    with pytest.raises(InvalidAttachmentError, match="unreadable"):
        inspect_pdf(BytesIO(b"%PDF-1.4 this is not really a pdf"))
