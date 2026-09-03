from __future__ import annotations

from lorex.domain import LibraryBook


def _book(index: int) -> LibraryBook:
    return LibraryBook(
        id=f"book-{index:03d}",
        title=f"Title {index:03d}",
        author=f"Author {index % 7:02d}",
        narrator=f"Narrator {index % 5:02d}",
        format="m4b",
        path=f"/library/Author {index % 7:02d}/Title {index:03d}/Title {index:03d}.m4b",
        size=1000 + index,
    )


def test_library_books_are_paginated_and_bounded(client):
    repository = client.app.state.container.library
    for index in range(120):
        repository.add(_book(index))

    response = client.get("/api/library/books", params={"limit": 50, "offset": 50})
    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] == 120
    assert payload["count"] == 50
    assert payload["limit"] == 50
    assert payload["offset"] == 50
    assert len(payload["books"]) == 50

    too_large = client.get("/api/library/books", params={"limit": 101})
    assert too_large.status_code == 422


def test_library_dashboard_reports_library_total(client):
    repository = client.app.state.container.library
    for index in range(3):
        repository.add(_book(index))

    response = client.get("/api/library/dashboard")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_books"] == 3
    assert "total_releases" in payload
    assert "download_statuses" in payload
    assert "import_statuses" in payload
