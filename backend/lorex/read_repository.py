from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from lorex.db_models import DownloadJobRow, LibraryBookRow, ReleaseArticleRow, ReleaseRow
from lorex.domain import DownloadJob, DownloadJobView
from lorex.postgres_repository import PostgresJobRepository, PostgresLibraryRepository, PostgresReleaseRepository
from lorex.search import LibraryPage, LibrarySearchQuery, LibrarySummary


class ResponsivePostgresReleaseRepository(PostgresReleaseRepository):
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        super().__init__(sessions)
        self._ui_sessions = sessions

    def count(self) -> int:
        with self._ui_sessions() as session:
            return int(session.scalar(select(func.count()).select_from(ReleaseRow)) or 0)


class ResponsivePostgresLibraryRepository(PostgresLibraryRepository):
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        super().__init__(sessions)
        self._ui_sessions = sessions

    def count(self) -> int:
        with self._ui_sessions() as session:
            return int(session.scalar(select(func.count()).select_from(LibraryBookRow)) or 0)

    def search_page(self, query: LibrarySearchQuery) -> LibraryPage:
        filters = []
        needle = query.q.casefold().strip()
        if needle:
            pattern = f"%{needle}%"
            filters.append(
                or_(
                    LibraryBookRow.title.ilike(pattern),
                    LibraryBookRow.author.ilike(pattern),
                    LibraryBookRow.narrator.ilike(pattern),
                )
            )

        sort_columns = {
            "title": LibraryBookRow.title,
            "author": LibraryBookRow.author,
            "narrator": LibraryBookRow.narrator,
            "format": LibraryBookRow.format,
            "size": LibraryBookRow.size,
        }
        direction = "desc" if query.order == "desc" else "asc"
        sort_column = sort_columns[query.sort]
        ordering = (getattr(sort_column, direction)(), getattr(LibraryBookRow.id, direction)())

        with self._ui_sessions() as session:
            total = int(session.scalar(select(func.count()).select_from(LibraryBookRow).where(*filters)) or 0)
            statement = (
                select(
                    LibraryBookRow.id,
                    LibraryBookRow.title,
                    LibraryBookRow.author,
                    LibraryBookRow.narrator,
                    LibraryBookRow.format,
                    LibraryBookRow.size,
                )
                .where(*filters)
                .order_by(*ordering)
                .limit(query.limit)
                .offset(query.offset)
            )
            results = tuple(LibrarySummary(*row) for row in session.execute(statement))

        return LibraryPage(total=total, limit=query.limit, offset=query.offset, results=results)


class ResponsivePostgresJobRepository(PostgresJobRepository):
    ACTIVE_STATUSES = ("queued", "downloading", "postprocessing", "importing")

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        super().__init__(sessions)
        self._ui_sessions = sessions

    def add(self, job: DownloadJob) -> DownloadJob:
        added = super().add(job)
        with self._ui_sessions.begin() as session:
            session.execute(
                update(ReleaseRow).where(ReleaseRow.id == job.release_id).values(download_status="queued")
            )
        return added

    def claim_next(self, worker_id: str) -> DownloadJob | None:
        job = super().claim_next(worker_id)
        if job is not None:
            with self._ui_sessions.begin() as session:
                session.execute(
                    update(ReleaseRow).where(ReleaseRow.id == job.release_id).values(download_status="downloading")
                )
        return job

    def pop_next(self) -> DownloadJob | None:
        return self.claim_next("compat")

    def status_counts(self) -> dict[str, int]:
        with self._ui_sessions() as session:
            return {
                str(status): int(count)
                for status, count in session.execute(
                    select(DownloadJobRow.status, func.count()).group_by(DownloadJobRow.status)
                ).all()
            }

    def find_active_for_release(self, release_id: str) -> DownloadJob | None:
        with self._ui_sessions() as session:
            row = session.execute(
                select(DownloadJobRow)
                .where(
                    DownloadJobRow.release_id == release_id,
                    DownloadJobRow.status.in_(self.ACTIVE_STATUSES),
                )
                .order_by(DownloadJobRow.created_order.desc())
                .limit(1)
            ).scalar_one_or_none()
            return None if row is None else DownloadJob(id=row.id, release_id=row.release_id, status=row.status)

    def list_recent(self, *, limit: int = 200, status: str | None = None) -> tuple[DownloadJobView, ...]:
        bounded = max(1, min(int(limit), 500))
        article_count = (
            select(func.count(ReleaseArticleRow.id))
            .where(ReleaseArticleRow.release_id == DownloadJobRow.release_id)
            .correlate(DownloadJobRow)
            .scalar_subquery()
        )
        statement = (
            select(
                DownloadJobRow,
                ReleaseRow.title,
                ReleaseRow.author,
                ReleaseRow.size,
                article_count,
            )
            .outerjoin(ReleaseRow, ReleaseRow.id == DownloadJobRow.release_id)
            .order_by(DownloadJobRow.created_order.desc())
            .limit(bounded)
        )
        if status is not None:
            statement = statement.where(DownloadJobRow.status == status)

        with self._ui_sessions() as session:
            rows = session.execute(statement).all()
            return tuple(
                DownloadJobView(
                    id=job.id,
                    release_id=job.release_id,
                    status=job.status,
                    bytes_completed=int(job.bytes_completed),
                    articles_completed=int(job.articles_completed),
                    total_articles=int(total_articles or 0),
                    error=job.error,
                    cancel_requested=bool(job.cancel_requested),
                    completed_at=job.completed_at,
                    updated_at=job.updated_at,
                    title=title,
                    author=author,
                    release_size=int(release_size) if release_size is not None else None,
                )
                for job, title, author, release_size, total_articles in rows
            )

    def set_runtime_status(self, job_id: str, status: str) -> None:
        now = datetime.now(UTC)
        with self._ui_sessions.begin() as session:
            row = session.get(DownloadJobRow, job_id, with_for_update=True)
            if row is None:
                return
            row.status = status
            row.updated_at = now
            session.execute(
                update(ReleaseRow).where(ReleaseRow.id == row.release_id).values(download_status=status)
            )

    def mark_completed(self, job_id: str) -> None:
        now = datetime.now(UTC)
        with self._ui_sessions.begin() as session:
            row = session.get(DownloadJobRow, job_id, with_for_update=True)
            if row is None:
                return
            row.status = "completed"
            row.error = None
            row.cancel_requested = False
            row.claimed_at = None
            row.claimed_by = None
            row.completed_at = now
            row.updated_at = now
            session.execute(
                update(ReleaseRow).where(ReleaseRow.id == row.release_id).values(
                    download_status="completed",
                    import_status="completed",
                )
            )

    def mark_failed(self, job_id: str, error: str | None = None) -> None:
        now = datetime.now(UTC)
        safe_error = error.strip()[:4096] if error else None
        with self._ui_sessions.begin() as session:
            row = session.get(DownloadJobRow, job_id, with_for_update=True)
            if row is None:
                return
            row.status = "failed"
            row.error = safe_error
            row.claimed_at = None
            row.claimed_by = None
            row.completed_at = now
            row.updated_at = now
            session.execute(
                update(ReleaseRow).where(ReleaseRow.id == row.release_id).values(download_status="failed")
            )

    def retry(self, job_id: str) -> DownloadJob | None:
        now = datetime.now(UTC)
        with self._ui_sessions.begin() as session:
            row = session.get(DownloadJobRow, job_id, with_for_update=True)
            if row is None or row.status not in {"failed", "canceled"}:
                return None
            row.status = "queued"
            row.error = None
            row.cancel_requested = False
            row.claimed_at = None
            row.claimed_by = None
            row.completed_at = None
            row.updated_at = now
            session.execute(
                update(ReleaseRow).where(ReleaseRow.id == row.release_id).values(download_status="queued")
            )
            return DownloadJob(id=row.id, release_id=row.release_id, status="queued")

    def request_cancel(self, job_id: str) -> DownloadJob | None:
        now = datetime.now(UTC)
        with self._ui_sessions.begin() as session:
            row = session.get(DownloadJobRow, job_id, with_for_update=True)
            if row is None or row.status in {"completed", "failed", "canceled"}:
                return None
            if row.status == "queued":
                row.status = "canceled"
                row.cancel_requested = False
                row.completed_at = now
                session.execute(
                    update(ReleaseRow).where(ReleaseRow.id == row.release_id).values(download_status="canceled")
                )
                status = "canceled"
            else:
                row.cancel_requested = True
                status = row.status
            row.updated_at = now
            return DownloadJob(id=row.id, release_id=row.release_id, status=status)

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._ui_sessions() as session:
            value = session.scalar(
                select(DownloadJobRow.cancel_requested).where(DownloadJobRow.id == job_id)
            )
            return bool(value)

    def mark_canceled(self, job_id: str) -> None:
        now = datetime.now(UTC)
        with self._ui_sessions.begin() as session:
            row = session.get(DownloadJobRow, job_id, with_for_update=True)
            if row is None:
                return
            row.status = "canceled"
            row.cancel_requested = False
            row.claimed_at = None
            row.claimed_by = None
            row.completed_at = now
            row.updated_at = now
            session.execute(
                update(ReleaseRow).where(ReleaseRow.id == row.release_id).values(download_status="canceled")
            )
