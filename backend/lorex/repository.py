from __future__ import annotations

from dataclasses import dataclass, field

from lorex.domain import DownloadJob, IndexedRelease, LibraryBook


@dataclass(slots=True)
class ReleaseRepository:
    _items: dict[str, IndexedRelease] = field(default_factory=dict)

    def add(self, release: IndexedRelease) -> IndexedRelease:
        self._items[release.id] = release
        return release

    def get(self, release_id: str) -> IndexedRelease | None:
        return self._items.get(release_id)

    def search(self, query: str) -> list[IndexedRelease]:
        needle = query.casefold().strip()
        values = list(self._items.values())
        if not needle:
            return values
        return [
            item
            for item in values
            if needle in item.title.casefold()
            or needle in item.author.casefold()
            or (item.narrator and needle in item.narrator.casefold())
            or needle in item.source_subject.casefold()
        ]


@dataclass(slots=True)
class JobRepository:
    _items: list[DownloadJob] = field(default_factory=list)

    def add(self, job: DownloadJob) -> DownloadJob:
        self._items.append(job)
        return job

    def pop_next(self) -> DownloadJob | None:
        if not self._items:
            return None
        return self._items.pop(0)


@dataclass(slots=True)
class LibraryRepository:
    _items: dict[str, LibraryBook] = field(default_factory=dict)

    def add(self, book: LibraryBook) -> LibraryBook:
        self._items[book.id] = book
        return book

    def all(self) -> list[LibraryBook]:
        return sorted(self._items.values(), key=lambda item: (item.author.casefold(), item.title.casefold()))
