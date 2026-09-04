from __future__ import annotations

import os
import re
import shutil
from hashlib import sha1
from pathlib import Path
from uuid import uuid4

from lorex.domain import DownloadResult, LibraryBook
from lorex.repository import LibraryRepository

_UNSAFE = re.compile(r"[\\/:*?\"<>|]+")
_SUPPORTED_AUDIO = {".m4b", ".m4a", ".mp3", ".aac", ".flac"}


def sanitize_component(value: str) -> str:
    cleaned = _UNSAFE.sub("-", value).strip().strip(".")
    return cleaned or "Unknown"


def _book_id(result: DownloadResult) -> str:
    return sha1(f"{result.author}|{result.title}|{result.narrator or ''}".encode("utf-8")).hexdigest()[:16]


class LibraryImporter:
    def __init__(self, repository: LibraryRepository, root: str = "/library") -> None:
        self.repository = repository
        self.root = root.rstrip("/")

    def _book(self, result: DownloadResult, *, path: str, format: str, size: int) -> LibraryBook:
        return LibraryBook(
            id=_book_id(result),
            title=result.title,
            author=result.author,
            narrator=result.narrator,
            format=format,
            path=path,
            size=size,
        )

    def import_file(self, result: DownloadResult, source_path: str | Path) -> LibraryBook:
        source = Path(source_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        extension = source.suffix.lower()
        if extension not in _SUPPORTED_AUDIO:
            raise ValueError(f"Unsupported audiobook file type: {extension or 'none'}")

        author = sanitize_component(result.author)
        title = sanitize_component(result.title)
        destination_dir = Path(self.root) / author / title
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{title}{extension}"

        if destination.exists() and destination.stat().st_size != source.stat().st_size:
            destination = destination_dir / f"{title}-{result.release_id[:8]}{extension}"

        created_destination = not destination.exists()
        if created_destination:
            temporary = destination_dir / f".{destination.name}.{uuid4().hex}.importing"
            try:
                with source.open("rb") as input_file, temporary.open("wb") as output_file:
                    shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
                    output_file.flush()
                    os.fsync(output_file.fileno())
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        elif destination.stat().st_size != source.stat().st_size:
            raise FileExistsError(destination)

        size = destination.stat().st_size
        book = self._book(
            result,
            path=str(destination),
            format=extension.lstrip("."),
            size=size,
        )
        try:
            persisted = self.repository.add(book)
        except Exception:
            if created_destination:
                destination.unlink(missing_ok=True)
            raise

        if source != destination:
            source.unlink(missing_ok=True)
        return persisted

    def import_download(self, result: DownloadResult) -> LibraryBook:
        """Legacy mock/import compatibility path.

        Production downloads use ``import_file`` after PostProcessor has produced
        an actual supported audio file. This method remains only for explicit mock
        API tests and callers that do not provide physical staging output.
        """
        author = sanitize_component(result.author)
        title = sanitize_component(result.title)
        file_name = f"{title}.{result.format}"
        path = f"{self.root}/{author}/{title}/{file_name}"
        book = self._book(result, path=path, format=result.format, size=result.size)
        return self.repository.add(book)
