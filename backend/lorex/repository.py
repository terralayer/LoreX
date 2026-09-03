from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from lorex.domain import (
    ArticleHeader,
    DownloadArticleState,
    DownloadJob,
    IndexCheckpoint,
    IndexedRelease,
    LibraryBook,
    ProviderHealthSnapshot,
)
from lorex.search import DashboardSummary, ReleaseSearchPage, ReleaseSearchQuery, ReleaseSummary


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

    def search_page(self, query: ReleaseSearchQuery) -> ReleaseSearchPage:
        values = self.search(query.q)
        if query.format is not None:
            values = [item for item in values if item.format == query.format]
        if query.download_status is not None or query.import_status is not None:
            values = []

        sort_keys = {
            "title": lambda item: item.title.casefold(),
            "author": lambda item: item.author.casefold(),
            "narrator": lambda item: (item.narrator or "").casefold(),
            "format": lambda item: item.format,
            "size": lambda item: item.size,
            "completion": lambda item: item.completion,
            "posted_at": lambda item: "",
        }
        values.sort(key=lambda item: (sort_keys[query.sort](item), item.id), reverse=query.order == "desc")
        total = len(values)
        values = values[query.offset : query.offset + query.limit]
        summaries = tuple(
            ReleaseSummary(
                id=item.id,
                title=item.title,
                author=item.author,
                narrator=item.narrator,
                format=item.format,
                size=item.size,
                completion=item.completion,
                download_status=None,
                import_status=None,
                posted_at=None,
            )
            for item in values
        )
        return ReleaseSearchPage(total, query.limit, query.offset, summaries)

    def dashboard_summary(self) -> DashboardSummary:
        return DashboardSummary(
            total_releases=len(self._items),
            download_statuses={"untracked": len(self._items)} if self._items else {},
            import_statuses={"untracked": len(self._items)} if self._items else {},
        )


@dataclass(slots=True)
class JobRepository:
    _items: deque[DownloadJob] = field(default_factory=deque)
    _jobs: dict[str, DownloadJob] = field(default_factory=dict)
    _claimed_at: dict[str, datetime] = field(default_factory=dict)
    _articles: dict[tuple[str, str], DownloadArticleState] = field(default_factory=dict)
    _progress: dict[str, tuple[int, int]] = field(default_factory=dict)
    _health: dict[str, ProviderHealthSnapshot] = field(default_factory=dict)

    def add(self, job: DownloadJob) -> DownloadJob:
        self._jobs[job.id] = job
        if job.status == "queued":
            self._items.append(job)
        return job

    def get(self, job_id: str) -> DownloadJob | None:
        return self._jobs.get(job_id)

    def claim_next(self, worker_id: str) -> DownloadJob | None:
        while self._items:
            queued = self._items.popleft()
            current = self._jobs.get(queued.id)
            if current is None or current.status != "queued":
                continue
            claimed = replace(current, status="downloading")
            self._jobs[claimed.id] = claimed
            self._claimed_at[claimed.id] = datetime.now(UTC)
            return claimed
        return None

    def pop_next(self) -> DownloadJob | None:
        return self.claim_next("compat")

    def mark_completed(self, job_id: str) -> None:
        job = self._jobs[job_id]
        self._jobs[job_id] = replace(job, status="completed")

    def mark_failed(self, job_id: str) -> None:
        job = self._jobs[job_id]
        self._jobs[job_id] = replace(job, status="failed")

    def recover_stale(self, stale_before: datetime) -> int:
        recovered = 0
        for job_id, claimed_at in list(self._claimed_at.items()):
            job = self._jobs.get(job_id)
            if job is None or job.status != "downloading" or claimed_at >= stale_before:
                continue
            queued = replace(job, status="queued")
            self._jobs[job_id] = queued
            self._items.append(queued)
            self._claimed_at.pop(job_id, None)
            recovered += 1
        return recovered

    def ensure_articles(self, job_id: str, articles: Iterable[ArticleHeader]) -> int:
        inserted = 0
        for article in articles:
            key = (job_id, article.message_id)
            if key not in self._articles:
                self._articles[key] = DownloadArticleState(job_id=job_id, message_id=article.message_id)
                inserted += 1
        return inserted

    def pending_articles(self, job_id: str, articles: Iterable[ArticleHeader]) -> tuple[ArticleHeader, ...]:
        materialized = tuple(articles)
        self.ensure_articles(job_id, materialized)
        return tuple(
            article
            for article in materialized
            if self._articles[(job_id, article.message_id)].status != "completed"
        )

    def mark_article_started(self, job_id: str, message_id: str, provider: str) -> None:
        key = (job_id, message_id)
        state = self._articles.get(key, DownloadArticleState(job_id=job_id, message_id=message_id))
        self._articles[key] = replace(
            state,
            status="in_progress",
            provider=provider,
            attempts=state.attempts + 1,
        )

    def mark_article_completed(
        self,
        job_id: str,
        message_id: str,
        provider: str,
        bytes_completed: int,
    ) -> None:
        key = (job_id, message_id)
        state = self._articles.get(key, DownloadArticleState(job_id=job_id, message_id=message_id))
        self._articles[key] = replace(
            state,
            status="completed",
            provider=provider,
            bytes_completed=bytes_completed,
        )

    def mark_article_failed(self, job_id: str, message_id: str, provider: str) -> None:
        key = (job_id, message_id)
        state = self._articles.get(key, DownloadArticleState(job_id=job_id, message_id=message_id))
        self._articles[key] = replace(state, status="failed", provider=provider)

    def persist_job_progress(self, job_id: str, *, bytes_delta: int, articles_delta: int = 0) -> None:
        bytes_completed, articles_completed = self._progress.get(job_id, (0, 0))
        self._progress[job_id] = (
            bytes_completed + bytes_delta,
            articles_completed + articles_delta,
        )

    def persist_progress(self, byte_count: int) -> None:
        # Compatibility sink for standalone ProgressCoalescer/streaming tests.
        return None

    def progress(self, job_id: str) -> tuple[int, int]:
        return self._progress.get(job_id, (0, 0))

    def record_provider_attempt(
        self,
        provider: str,
        *,
        success: bool,
        fallback: bool,
        byte_count: int,
        elapsed_ms: float,
    ) -> None:
        snapshot = self._health.get(provider, ProviderHealthSnapshot(provider=provider))
        self._health[provider] = ProviderHealthSnapshot(
            provider=provider,
            attempts=snapshot.attempts + 1,
            successes=snapshot.successes + int(success),
            failures=snapshot.failures + int(not success),
            fallbacks=snapshot.fallbacks + int(fallback),
            bytes_delivered=snapshot.bytes_delivered + byte_count,
            elapsed_ms_total=snapshot.elapsed_ms_total + elapsed_ms,
        )

    def provider_health(self, provider: str) -> ProviderHealthSnapshot:
        return self._health.get(provider, ProviderHealthSnapshot(provider=provider))


@dataclass(slots=True)
class LibraryRepository:
    _items: dict[str, LibraryBook] = field(default_factory=dict)

    def add(self, book: LibraryBook) -> LibraryBook:
        self._items[book.id] = book
        return book

    def all(self) -> list[LibraryBook]:
        return sorted(self._items.values(), key=lambda item: (item.author.casefold(), item.title.casefold()))
