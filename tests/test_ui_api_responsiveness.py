from __future__ import annotations

from lorex.domain import LibraryBook
from lorex.repository import LibraryRepository


def _book(index: int) -> LibraryBook:
    return LibraryBook(
        id=f"book-{index:03d}",
        title=f"Book {index:03d}",
        author="Example Author",
        narrator="Example Narrator",
        format="m4b",
        path=f"/library/Example Author/Book {index:03d}/Book {index:03d}.m4b",
        size=1_000_000 + index,
    )


def test_library_books_api_is_server_paginated(client):
    library = LibraryRepository()
    for index in range(6):
        library.add(_book(index))
    client.app.state.container.library = library

    response = client.get(
        "/api/library/books",
        params={"limit": 2, "offset": 2, "q": "book", "sort": "title", "order": "asc"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 6
    assert payload["limit"] == 2
    assert payload["offset"] == 2
    assert [item["id"] for item in payload["results"]] == ["book-002", "book-003"]
    assert len(payload["results"]) <= 2
    assert "books" not in payload


def test_dashboard_uses_lightweight_counts_not_library_all(client):
    class CountOnlyLibrary(LibraryRepository):
        def all(self):  # pragma: no cover - this must never be reached
            raise AssertionError("dashboard must not materialize the full library")

    library = CountOnlyLibrary()
    for index in range(4):
        library.add(_book(index))
    client.app.state.container.library = library

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["library_books"] == 4
    assert payload["total_releases"] == 0
    assert payload["active_downloads"] == 0
    assert payload["queued_downloads"] == 0
