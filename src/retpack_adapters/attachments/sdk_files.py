"""``FilesClient`` over ``databricks-sdk`` Files API (Unity Catalog Volumes)."""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, BinaryIO

from retpack_adapters.attachments.files_client import FileEntry


class SdkFilesClient:
    """Wraps a ``WorkspaceClient``; imported lazily so the mock backend needs no SDK."""

    def __init__(self, workspace_client: Any) -> None:
        self._w = workspace_client

    def upload(self, path: str, stream: BinaryIO) -> None:
        """See ``FilesClient.upload``."""
        self._w.files.upload(path, stream, overwrite=True)

    def download(self, path: str) -> BinaryIO:
        """See ``FilesClient.download``."""
        try:
            response = self._w.files.download(path)
        except Exception as exc:  # the SDK raises NotFound (a ``DatabricksError`` subclass)
            if type(exc).__name__ == "NotFound":
                raise FileNotFoundError(path) from exc
            raise
        contents: BinaryIO = response.contents
        return contents

    def delete(self, path: str) -> None:
        """See ``FilesClient.delete``."""
        try:
            self._w.files.delete(path)
        except Exception as exc:
            if type(exc).__name__ != "NotFound":
                raise

    def list(self, prefix: str) -> Iterable[FileEntry]:
        """See ``FilesClient.list``. Walks directories recursively."""
        out: list[FileEntry] = []
        stack = [prefix.rstrip("/")]
        while stack:
            directory = stack.pop()
            for entry in self._w.files.list_directory_contents(directory):
                if entry.is_directory:
                    stack.append(entry.path)
                else:
                    modified = datetime.fromtimestamp((entry.last_modified or 0) / 1000, tz=UTC)
                    out.append(FileEntry(path=entry.path, size=int(entry.file_size or 0), modified_at=modified))
        return out
