"""In-memory ``FilesClient`` for tests and local runs."""

from collections.abc import Iterable
from datetime import UTC, datetime
from io import BytesIO
from typing import BinaryIO

from retpack_adapters.attachments.files_client import FileEntry


class InMemoryFilesClient:
    """Dict of path to bytes."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, datetime]] = {}

    def upload(self, path: str, stream: BinaryIO) -> None:
        """See ``FilesClient.upload``."""
        self.objects[path] = (stream.read(), datetime.now(UTC))

    def download(self, path: str) -> BinaryIO:
        """See ``FilesClient.download``."""
        if path not in self.objects:
            raise FileNotFoundError(path)
        return BytesIO(self.objects[path][0])

    def delete(self, path: str) -> None:
        """See ``FilesClient.delete``."""
        self.objects.pop(path, None)

    def list(self, prefix: str) -> Iterable[FileEntry]:
        """See ``FilesClient.list``."""
        return [FileEntry(path=p, size=len(b), modified_at=t) for p, (b, t) in self.objects.items() if p.startswith(prefix.rstrip("/") + "/")]
