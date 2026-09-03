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


def test_short_reads_do_not_break_the_header_check():
    class Trickle(BytesIO):
        def read(self, n: int = -1) -> bytes:
            return super().read(2)

    dst = BytesIO()
    copy_and_hash(Trickle(SAMPLE), dst, max_bytes=1_000_000)
    assert dst.getvalue() == SAMPLE


@pytest.mark.parametrize(
    "body",
    [
        b"GIF89a.....",
        b"<html><script>alert(1)</script><!-- %PDF-1.4 -->" + SAMPLE,
        b"PK\x03\x04zipzip" + SAMPLE,
        b"\n" * 100 + b"%PDF-1.4 rest",
    ],
)
def test_rejects_anything_not_starting_with_pdf_header(body: bytes):
    with pytest.raises(InvalidAttachmentError, match="not a PDF"):
        copy_and_hash(BytesIO(body), BytesIO(), max_bytes=1_000_000)


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


def test_inspect_text_pdf(tmp_path: Path):
    p = tmp_path / "s.pdf"
    p.write_bytes(SAMPLE)
    info = inspect_pdf(p)
    assert info.page_count == 1 and info.has_text_layer is True


def test_inspect_scanned_pdf(tmp_path: Path):
    p = tmp_path / "s.pdf"
    p.write_bytes(SCANNED)
    info = inspect_pdf(p)
    assert info.page_count == 1 and info.has_text_layer is False


def test_inspect_corrupt_pdf_gives_fixed_message(tmp_path: Path):
    p = tmp_path / "c.pdf"
    p.write_bytes(b"%PDF-1.4 this is not really a pdf")
    with pytest.raises(InvalidAttachmentError) as exc:
        inspect_pdf(p)
    assert str(exc.value) == "unreadable PDF"


def test_inspect_timeout_rejects(tmp_path: Path):
    p = tmp_path / "s.pdf"
    p.write_bytes(SAMPLE)
    with pytest.raises(InvalidAttachmentError, match="could not be inspected"):
        inspect_pdf(p, timeout_s=0.001)
