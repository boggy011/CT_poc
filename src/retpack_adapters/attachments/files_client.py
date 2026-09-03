"""Thin client protocol over the Databricks Files API, so the Volume store can be tested without a workspace."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class FileEntry:
    """One object listed under a Volume prefix."""

    path: str
    size: int
    modified_at: datetime


class FilesClient(Protocol):
    """The four operations the store and the reaper need."""

    def upload(self, path: str, stream: BinaryIO) -> None:
        """Create or replace the object at ``path`` from a binary stream."""
        ...

    def download(self, path: str) -> BinaryIO:
        """Open the object for reading; caller closes.

        Raises:
            FileNotFoundError: If missing.
        """
        ...

    def delete(self, path: str) -> None:
        """Remove the object; missing objects are ignored."""
        ...

    def list(self, prefix: str) -> Iterable[FileEntry]:
        """Recursively list objects under a directory prefix."""
        ...
