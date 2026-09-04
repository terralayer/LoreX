from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from lorex.db_models import DownloadJobRow, LibraryBookRow, ReleaseRow
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
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        super().__init__(sessions)
        self._ui_sessions = sessions

    def status_counts(self) -> dict[str, int]:
        with self._ui_sessions() as session:
            return {
                str(status): int(count)
                for status, count in session.execute(
                    select(DownloadJobRow.status, func.count()).group_by(DownloadJobRow.status)
                ).all()
            }
