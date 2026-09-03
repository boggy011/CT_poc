"""Child-process entry point for PDF inspection. Run as ``python -m retpack_core.pdf_inspect <path> <memory_mb>``.

Kept separate from ``retpack_core.pdf`` so the parent never imports ``pypdf``
on the request path and the child never imports Streamlit.
"""

import json
import sys

TEXT_LAYER_PAGES = 3


def _limit_memory(memory_mb: int) -> None:
    try:
        import resource

        limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):
        pass


def inspect(path: str) -> dict[str, object]:
    """Count pages and detect a text layer in the first pages."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    page_count = len(reader.pages)
    has_text = any(page.extract_text().strip() for page in reader.pages[:TEXT_LAYER_PAGES])
    return {"ok": True, "page_count": page_count, "has_text_layer": has_text}


def main(argv: list[str]) -> int:
    """CLI entry; prints one JSON object to stdout."""
    path, memory_mb = argv[1], int(argv[2])
    _limit_memory(memory_mb)
    try:
        result = inspect(path)
    except BaseException as exc:  # report everything; the parent decides
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
