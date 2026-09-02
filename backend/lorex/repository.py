from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from lorex.domain import ArticleHeader, DownloadJob, IndexCheckpoint, IndexedRelease, LibraryBook


@dataclass(slots=True)
class ReleaseRepository:
    _items: dict[str, IndexedRelease] = field(default_factory=dict)
    _articles: dict[str, tuple[ArticleHeader, ...]] = field(default_factory=dict)
    _checkpoints: dict[tuple[str, str], IndexCheckpoint] = field(default_factory=dict)
    _nzb_cache: dict[str, str] = field(default_factory=dict)

    def add(self, release: IndexedRelease) -> IndexedRelease:
        self._items[release.id] = release
        return release

    def get(self, release_id: str) -> IndexedRelease | None:
        return self._items.get(release_id)

    def commit_index_batch(
        self,
        records: Iterable[tuple[IndexedRelease, tuple[ArticleHeader, ...]]],
        checkpoint: IndexCheckpoint | None = None,
    ) -> int:
        batch = list(records)

        if checkpoint is not None:
            if checkpoint.article_number < 0:
                raise ValueError("checkpoint article number cannot be negative")
            key = (checkpoint.source, checkpoint.group)
            previous = self._checkpoints.get(key)
            if previous is not None and checkpoint.article_number < previous.article_number:
                raise ValueError("checkpoint cannot move backwards")

        inserted = 0
        for release, articles in batch:
            if release.id in self._items:
                continue
            self._items[release.id] = release
            self._articles[release.id] = tuple(articles)
            inserted += 1

        if checkpoint is not None:
            self._checkpoints[(checkpoint.source, checkpoint.group)] = checkpoint

        return inserted

    def get_checkpoint(self, source: str, group: str) -> IndexCheckpoint | None:
        return self._checkpoints.get((source, group))

    def get_articles(self, release_id: str) -> tuple[ArticleHeader, ...]:
        return self._articles.get(release_id, ())

    def get_cached_nzb(self, release_id: str) -> str | None:
        return self._nzb_cache.get(release_id)

    def cache_nzb(self, release_id: str, nzb: str) -> str:
        self._nzb_cache[release_id] = nzb
        return nzb

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
