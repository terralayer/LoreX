from __future__ import annotations

from sqlalchemy import func, select

from lorex.db_models import LibraryBookRow
from lorex.domain import LibraryBook
from lorex.postgres_repository import PostgresLibraryRepository
from lorex.repository import LibraryRepository


def _book_from_row(row: LibraryBookRow) -> LibraryBook:
    return LibraryBook(
        id=row.id,
        title=row.title,
        author=row.author,
        narrator=row.narrator,
        format=row.format,
        path=row.path,
        size=row.size,
    )


class PagedLibraryRepository(LibraryRepository):
    def count(self) -> int:
        return len(self._items)

    def page(self, *, limit: int, offset: int) -> list[LibraryBook]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if offset < 0:
            raise ValueError("offset must be nonnegative")
        values = sorted(
            self._items.values(),
            key=lambda item: (item.author.casefold(), item.title.casefold(), item.id),
        )
        return values[offset : offset + limit]


class PagedPostgresLibraryRepository(PostgresLibraryRepository):
    def count(self) -> int:
        with self._sessions() as session:
            return int(session.scalar(select(func.count()).select_from(LibraryBookRow)) or 0)

    def page(self, *, limit: int, offset: int) -> list[LibraryBook]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if offset < 0:
            raise ValueError("offset must be nonnegative")
        with self._sessions() as session:
            rows = session.execute(
                select(LibraryBookRow)
                .order_by(LibraryBookRow.author, LibraryBookRow.title, LibraryBookRow.id)
                .limit(limit)
                .offset(offset)
            ).scalars()
            return [_book_from_row(row) for row in rows]
