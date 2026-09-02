from __future__ import annotations

from collections.abc import Iterable, Iterator

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from lorex.db_models import (
    DownloadJobRow,
    IndexerCheckpointRow,
    LibraryBookRow,
    ReleaseArticleRow,
    ReleaseRow,
)
from lorex.domain import ArticleHeader, DownloadJob, IndexCheckpoint, IndexedRelease, LibraryBook

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
                if (
                    checkpoint_row is not None
                    and checkpoint.article_number < checkpoint_row.article_number
                ):
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
            nzb = session.execute(
                select(ReleaseRow.nzb).where(ReleaseRow.id == release_id)
            ).scalar_one_or_none()
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
            rows = session.execute(
                select(LibraryBookRow).order_by(LibraryBookRow.author, LibraryBookRow.title)
            ).scalars()
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
        with self._sessions.begin() as session:
            statement = pg_insert(DownloadJobRow).values(
                id=job.id,
                release_id=job.release_id,
                status=job.status,
            )
            statement = statement.on_conflict_do_update(
                index_elements=[DownloadJobRow.id],
                set_={"release_id": job.release_id, "status": job.status},
            )
            session.execute(statement)
        return job

    def pop_next(self) -> DownloadJob | None:
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
            job = DownloadJob(id=row.id, release_id=row.release_id, status=row.status)
            session.execute(delete(DownloadJobRow).where(DownloadJobRow.id == row.id))
            return job
