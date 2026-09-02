from __future__ import annotations

import re
from hashlib import sha1

from lorex.domain import DownloadResult, LibraryBook
from lorex.repository import LibraryRepository

_UNSAFE = re.compile(r"[\\/:*?\"<>|]+")


def sanitize_component(value: str) -> str:
    cleaned = _UNSAFE.sub("-", value).strip().strip(".")
    return cleaned or "Unknown"


class LibraryImporter:
    def __init__(self, repository: LibraryRepository, root: str = "/library") -> None:
        self.repository = repository
        self.root = root.rstrip("/")

    def import_download(self, result: DownloadResult) -> LibraryBook:
        author = sanitize_component(result.author)
        title = sanitize_component(result.title)
        file_name = f"{title}.{result.format}"
        path = f"{self.root}/{author}/{title}/{file_name}"
        book_id = sha1(f"{result.author}|{result.title}|{result.narrator or ''}".encode("utf-8")).hexdigest()[:16]
        book = LibraryBook(
            id=book_id,
            title=result.title,
            author=result.author,
            narrator=result.narrator,
            format=result.format,
            path=path,
            size=result.size,
        )
        return self.repository.add(book)
