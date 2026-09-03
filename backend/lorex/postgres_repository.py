from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from lorex.db_models import (
    DownloadArticleRow,
    DownloadJobRow,
    IndexerCheckpointRow,
    LibraryBookRow,
    ProviderHealthRow,
    ReleaseArticleRow,
    ReleaseRow,
)
from lorex.domain import (
    ArticleHeader,
    DownloadJob,
    IndexCheckpoint,
    IndexedRelease,
    LibraryBook,
    ProviderHealthSnapshot,
)
from lorex.search import DashboardSummary, ReleaseSearchPage, ReleaseSearchQuery, ReleaseSummary

_POSTGRES_BIND_BUDGET = 60_000
_RELEASE_BIND_COLUMNS = 13
_ARTICLE_BIND_COLUMNS = 5


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _chunks[T](values: list[T], columns_per_row: int) -> Iterator[list[T]]:
    chunk_size = max(1, _POSTGRES_BIND_BUDGET // columns_per_row)
    for offset in range(0, len(values), chunk_size):
        yield values[offset : offset + chunk_size]


def _release_values(release: IndexedRelease) -> dict[str, object]:
    normalized_title = _normalize(release.title)
    normalized_author = _normalize(release.author)
    return {
        "id": release.id,
        "title": release.title,
        "normalized_title": normalized_title,
        "author": release.author,
        "normalized_author": normalized_author,
        "narrator": release.narrator,
        "format": release.format,
        "size": release.size,
        "completion": release.completion,
        "source_subject": release.source_subject,
        "nzb": release.nzb,
        "fingerprint": release.id,
        "wanted_key": f"{normalized_author}|{normalized_title}",
    }


def _to_release(row: ReleaseRow) -> IndexedRelease:
    return IndexedRelease(
        id=row.id,
        title=row.title,
        author=row.author,
        narrator=row.narrator,
        format=row.format,
        size=row.size,
        completion=row.completion,
        nzb=row.nzb,
        source_subject=row.source_subject,
    )


class PostgresReleaseRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def add(self, release: IndexedRelease) -> IndexedRelease:
        values = _release_values(release)
        with self._sessions.begin() as session:
            statement = pg_insert(ReleaseRow).values(values)
            statement = statement.on_conflict_do_update(
                index_elements=[ReleaseRow.id],
                set_={
                    key: value
                    for key, value in values.items()
                    if key not in {"id", "fingerprint"}
                },
            )
            session.execute(statement)
        return release

    def get(self, release_id: str) -> IndexedRelease | None:
        with self._sessions() as session:
            row = session.get(ReleaseRow, release_id)
            return None if row is None else _to_release(row)

    def commit_index_batch(
        self,
        records: Iterable[tuple[IndexedRelease, tuple[ArticleHeader, ...]]],
        checkpoint: IndexCheckpoint | None = None,
    ) -> int:
        batch = list(records)
        if checkpoint is not None and checkpoint.article_number < 0:
            raise ValueError("checkpoint article number cannot be negative")

        with self._sessions.begin() as session:
            if checkpoint is not None:
                checkpoint_row = session.execute(
                    select(IndexerCheckpointRow)
                    .where(
                        IndexerCheckpointRow.source == checkpoint.source,
                        IndexerCheckpointRow.group == checkpoint.group,
                    )
                    .with_for_update()
                ).scalar_one_or_none()
                if checkpoint_row is not None and checkpoint.article_number < checkpoint_row.article_number:
                    raise ValueError("checkpoint cannot move backwards")

            inserted_ids: set[str] = set()
            if batch:
                release_values = [_release_values(release) for release, _ in batch]
                for release_chunk in _chunks(release_values, _RELEASE_BIND_COLUMNS):
                    statement = (
                        pg_insert(ReleaseRow)
                        .values(release_chunk)
                        .on_conflict_do_nothing()
                        .returning(ReleaseRow.id)
                    )
                    inserted_ids.update(session.execute(statement).scalars())

                article_values = [
                    {
                        "release_id": release.id,
                        "message_id": article.message_id,
                        "subject": article.subject,
                        "bytes": article.bytes,
                        "group": article.group,
                    }
                    for release, articles in batch
                    if release.id in inserted_ids
                    for article in articles
                ]
                for article_chunk in _chunks(article_values, _ARTICLE_BIND_COLUMNS):
                    session.execute(
                        pg_insert(ReleaseArticleRow)
                        .values(article_chunk)
                        .on_conflict_do_nothing(index_elements=[ReleaseArticleRow.message_id])
                    )

            if checkpoint is not None:
                statement = pg_insert(IndexerCheckpointRow).values(
                    source=checkpoint.source,
                    group=checkpoint.group,
                    article_number=checkpoint.article_number,
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[IndexerCheckpointRow.source, IndexerCheckpointRow.group],
                    set_={"article_number": checkpoint.article_number},
                )
                session.execute(statement)

        return len(inserted_ids)

    def get_checkpoint(self, source: str, group: str) -> IndexCheckpoint | None:
        with self._sessions() as session:
            row = session.get(IndexerCheckpointRow, (source, group))
            if row is None:
                return None
            return IndexCheckpoint(row.source, row.group, row.article_number)

    def get_articles(self, release_id: str) -> tuple[ArticleHeader, ...]:
        with self._sessions() as session:
            rows = session.execute(
                select(ReleaseArticleRow)
                .where(ReleaseArticleRow.release_id == release_id)
                .order_by(ReleaseArticleRow.id)
            ).scalars()
            return tuple(
                ArticleHeader(
                    message_id=row.message_id,
                    subject=row.subject,
                    bytes=row.bytes,
                    group=row.group,
                )
                for row in rows
            )

    def get_cached_nzb(self, release_id: str) -> str | None:
        with self._sessions() as session:
            nzb = session.execute(select(ReleaseRow.nzb).where(ReleaseRow.id == release_id)).scalar_one_or_none()
            return nzb or None

    def cache_nzb(self, release_id: str, nzb: str) -> str:
        with self._sessions.begin() as session:
            session.execute(update(ReleaseRow).where(ReleaseRow.id == release_id).values(nzb=nzb))
        return nzb

    def search(self, query: str) -> list[IndexedRelease]:
        needle = query.casefold().strip()
        with self._sessions() as session:
            statement = select(ReleaseRow)
            if needle:
                pattern = f"%{needle}%"
                statement = statement.where(
                    or_(
                        ReleaseRow.normalized_title.like(pattern),
                        ReleaseRow.normalized_author.like(pattern),
                        ReleaseRow.narrator.ilike(pattern),
                        ReleaseRow.source_subject.ilike(pattern),
                    )
                )
            rows = session.execute(statement.order_by(ReleaseRow.id)).scalars()
            return [_to_release(row) for row in rows]

    def search_page(self, query: ReleaseSearchQuery) -> ReleaseSearchPage:
        filters = []
        needle = query.q.casefold().strip()
        if needle:
            pattern = f"%{needle}%"
            filters.append(
                or_(
                    ReleaseRow.normalized_title.ilike(pattern),
                    ReleaseRow.normalized_author.ilike(pattern),
                    ReleaseRow.narrator.ilike(pattern),
                    ReleaseRow.source_subject.ilike(pattern),
                )
            )
        if query.format is not None:
            filters.append(ReleaseRow.format == query.format)
        if query.download_status is not None:
            filters.append(ReleaseRow.download_status == query.download_status)
        if query.import_status is not None:
            filters.append(ReleaseRow.import_status == query.import_status)

        sort_columns = {
            "title": ReleaseRow.normalized_title,
            "author": ReleaseRow.normalized_author,
            "narrator": ReleaseRow.narrator,
            "format": ReleaseRow.format,
            "size": ReleaseRow.size,
            "completion": ReleaseRow.completion,
            "posted_at": ReleaseRow.posted_at,
        }
        sort_column = sort_columns[query.sort]
        direction = "desc" if query.order == "desc" else "asc"
        ordering = (getattr(sort_column, direction)(), getattr(ReleaseRow.id, direction)())

        with self._sessions() as session:
            total = session.scalar(select(func.count()).select_from(ReleaseRow).where(*filters)) or 0
            statement = (
                select(
                    ReleaseRow.id,
                    ReleaseRow.title,
                    ReleaseRow.author,
                    ReleaseRow.narrator,
                    ReleaseRow.format,
                    ReleaseRow.size,
                    ReleaseRow.completion,
                    ReleaseRow.download_status,
                    ReleaseRow.import_status,
                    ReleaseRow.posted_at,
                )
                .where(*filters)
                .order_by(*ordering)
                .limit(query.limit)
                .offset(query.offset)
            )
            results = tuple(ReleaseSummary(*row) for row in session.execute(statement))

        return ReleaseSearchPage(total=total, limit=query.limit, offset=query.offset, results=results)

    def dashboard_summary(self) -> DashboardSummary:
        download_status = func.coalesce(ReleaseRow.download_status, "untracked")
        import_status = func.coalesce(ReleaseRow.import_status, "untracked")
        with self._sessions() as session:
            total = session.scalar(select(func.count()).select_from(ReleaseRow)) or 0
            download_counts = dict(session.execute(select(download_status, func.count()).group_by(download_status)).all())
            import_counts = dict(session.execute(select(import_status, func.count()).group_by(import_status)).all())
        return DashboardSummary(total, download_counts, import_counts)


class PostgresLibraryRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def add(self, book: LibraryBook) -> LibraryBook:
        values = {
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "narrator": book.narrator,
            "format": book.format,
            "path": book.path,
            "size": book.size,
        }
        with self._sessions.begin() as session:
            statement = pg_insert(LibraryBookRow).values(values)
            statement = statement.on_conflict_do_update(
                index_elements=[LibraryBookRow.id],
                set_={key: value for key, value in values.items() if key != "id"},
            )
            session.execute(statement)
        return book

    def all(self) -> list[LibraryBook]:
        with self._sessions() as session:
            rows = session.execute(select(LibraryBookRow).order_by(LibraryBookRow.author, LibraryBookRow.title)).scalars()
            return [
                LibraryBook(
                    id=row.id,
                    title=row.title,
                    author=row.author,
                    narrator=row.narrator,
                    format=row.format,
                    path=row.path,
                    size=row.size,
                )
                for row in rows
            ]


class PostgresJobRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def add(self, job: DownloadJob) -> DownloadJob:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            statement = pg_insert(DownloadJobRow).values(
                id=job.id,
                release_id=job.release_id,
                status=job.status,
                bytes_completed=0,
                articles_completed=0,
                updated_at=now,
            )
            statement = statement.on_conflict_do_update(
                index_elements=[DownloadJobRow.id],
                set_={"release_id": job.release_id, "status": job.status, "updated_at": now},
            )
            session.execute(statement)
        return job

    def get(self, job_id: str) -> DownloadJob | None:
        with self._sessions() as session:
            row = session.get(DownloadJobRow, job_id)
            if row is None:
                return None
            return DownloadJob(id=row.id, release_id=row.release_id, status=row.status)

    def claim_next(self, worker_id: str) -> DownloadJob | None:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            row = session.execute(
                select(DownloadJobRow)
                .where(DownloadJobRow.status == "queued")
                .order_by(DownloadJobRow.created_order)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).scalar_one_or_none()
            if row is None:
                return None
            row.status = "downloading"
            row.claimed_at = now
            row.claimed_by = worker_id
            row.updated_at = now
            session.flush()
            return DownloadJob(id=row.id, release_id=row.release_id, status=row.status)

    def pop_next(self) -> DownloadJob | None:
        return self.claim_next("compat")

    def mark_completed(self, job_id: str) -> None:
        self._set_status(job_id, "completed")

    def mark_failed(self, job_id: str) -> None:
        self._set_status(job_id, "failed")

    def _set_status(self, job_id: str, status: str) -> None:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            session.execute(
                update(DownloadJobRow)
                .where(DownloadJobRow.id == job_id)
                .values(status=status, claimed_at=None, claimed_by=None, updated_at=now)
            )

    def recover_stale(self, stale_before: datetime) -> int:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            result = session.execute(
                update(DownloadJobRow)
                .where(
                    DownloadJobRow.status == "downloading",
                    DownloadJobRow.claimed_at.is_not(None),
                    DownloadJobRow.claimed_at < stale_before,
                )
                .values(status="queued", claimed_at=None, claimed_by=None, updated_at=now)
            )
            return int(result.rowcount or 0)

    def ensure_articles(self, job_id: str, articles: Iterable[ArticleHeader]) -> int:
        materialized = tuple(articles)
        if not materialized:
            return 0
        now = datetime.now(UTC)
        values = [
            {
                "job_id": job_id,
                "message_id": article.message_id,
                "status": "pending",
                "bytes_completed": 0,
                "attempts": 0,
                "updated_at": now,
            }
            for article in materialized
        ]
        with self._sessions.begin() as session:
            statement = (
                pg_insert(DownloadArticleRow)
                .values(values)
                .on_conflict_do_nothing(constraint="ux_download_articles_job_message")
                .returning(DownloadArticleRow.id)
            )
            return len(tuple(session.execute(statement).scalars()))

    def pending_articles(self, job_id: str, articles: Iterable[ArticleHeader]) -> tuple[ArticleHeader, ...]:
        materialized = tuple(articles)
        self.ensure_articles(job_id, materialized)
        with self._sessions() as session:
            completed = set(
                session.execute(
                    select(DownloadArticleRow.message_id).where(
                        DownloadArticleRow.job_id == job_id,
                        DownloadArticleRow.status == "completed",
                    )
                ).scalars()
            )
        return tuple(article for article in materialized if article.message_id not in completed)

    def mark_article_started(self, job_id: str, message_id: str, provider: str) -> None:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            session.execute(
                update(DownloadArticleRow)
                .where(DownloadArticleRow.job_id == job_id, DownloadArticleRow.message_id == message_id)
                .values(
                    status="in_progress",
                    provider=provider,
                    attempts=DownloadArticleRow.attempts + 1,
                    updated_at=now,
                )
            )

    def mark_article_completed(
        self,
        job_id: str,
        message_id: str,
        provider: str,
        bytes_completed: int,
    ) -> None:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            session.execute(
                update(DownloadArticleRow)
                .where(DownloadArticleRow.job_id == job_id, DownloadArticleRow.message_id == message_id)
                .values(
                    status="completed",
                    provider=provider,
                    bytes_completed=bytes_completed,
                    updated_at=now,
                )
            )
            session.execute(
                update(DownloadJobRow)
                .where(DownloadJobRow.id == job_id)
                .values(articles_completed=DownloadJobRow.articles_completed + 1, updated_at=now)
            )

    def mark_article_failed(self, job_id: str, message_id: str, provider: str) -> None:
        with self._sessions.begin() as session:
            session.execute(
                update(DownloadArticleRow)
                .where(DownloadArticleRow.job_id == job_id, DownloadArticleRow.message_id == message_id)
                .values(status="failed", provider=provider, updated_at=datetime.now(UTC))
            )

    def persist_job_progress(self, job_id: str, *, bytes_delta: int, articles_delta: int = 0) -> None:
        with self._sessions.begin() as session:
            session.execute(
                update(DownloadJobRow)
                .where(DownloadJobRow.id == job_id)
                .values(
                    bytes_completed=DownloadJobRow.bytes_completed + bytes_delta,
                    articles_completed=DownloadJobRow.articles_completed + articles_delta,
                    updated_at=datetime.now(UTC),
                )
            )

    def persist_progress(self, byte_count: int) -> None:
        return None

    def progress(self, job_id: str) -> tuple[int, int]:
        with self._sessions() as session:
            row = session.execute(
                select(DownloadJobRow.bytes_completed, DownloadJobRow.articles_completed).where(
                    DownloadJobRow.id == job_id
                )
            ).one()
            return int(row[0]), int(row[1])

    def record_provider_attempt(
        self,
        provider: str,
        *,
        success: bool,
        fallback: bool,
        byte_count: int,
        elapsed_ms: float,
    ) -> None:
        now = datetime.now(UTC)
        values = {
            "provider": provider,
            "attempts": 1,
            "successes": int(success),
            "failures": int(not success),
            "fallbacks": int(fallback),
            "bytes_delivered": byte_count,
            "elapsed_ms_total": elapsed_ms,
            "updated_at": now,
        }
        with self._sessions.begin() as session:
            statement = pg_insert(ProviderHealthRow).values(values)
            statement = statement.on_conflict_do_update(
                index_elements=[ProviderHealthRow.provider],
                set_={
                    "attempts": ProviderHealthRow.attempts + 1,
                    "successes": ProviderHealthRow.successes + int(success),
                    "failures": ProviderHealthRow.failures + int(not success),
                    "fallbacks": ProviderHealthRow.fallbacks + int(fallback),
                    "bytes_delivered": ProviderHealthRow.bytes_delivered + byte_count,
                    "elapsed_ms_total": ProviderHealthRow.elapsed_ms_total + elapsed_ms,
                    "updated_at": now,
                },
            )
            session.execute(statement)

    def provider_health(self, provider: str) -> ProviderHealthSnapshot:
        with self._sessions() as session:
            row = session.get(ProviderHealthRow, provider)
            if row is None:
                return ProviderHealthSnapshot(provider=provider)
            return ProviderHealthSnapshot(
                provider=row.provider,
                attempts=row.attempts,
                successes=row.successes,
                failures=row.failures,
                fallbacks=row.fallbacks,
                bytes_delivered=row.bytes_delivered,
                elapsed_ms_total=row.elapsed_ms_total,
            )
