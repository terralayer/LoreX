from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from lorex.db import session_factory
from lorex.db_models import Base, ReleaseRow
from lorex.postgres_repository import PostgresReleaseRepository
from lorex.search import ReleaseSearchQuery


@pytest.fixture()
def repository() -> PostgresReleaseRepository:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    with sessions.begin() as session:
        session.add_all(
            [
                _row("release-3", "The Way of Kings", "Brandon Sanderson", "Kate Reading", "m4b", "completed", "imported", 3),
                _row("release-1", "Project Hail Mary", "Andy Weir", "Ray Porter", "m4b", "queued", "pending", 1),
                _row("release-2", "Project Hail Mary", "Andy Weir", None, "mp3", "completed", "pending", 2),
            ]
        )
    yield PostgresReleaseRepository(sessions)
    engine.dispose()


def _row(
    release_id: str,
    title: str,
    author: str,
    narrator: str | None,
    format: str,
    download_status: str,
    import_status: str,
    day: int,
) -> ReleaseRow:
    return ReleaseRow(
        id=release_id,
        title=title,
        normalized_title=title.casefold(),
        author=author,
        normalized_author=author.casefold(),
        narrator=narrator,
        format=format,
        size=123_456,
        completion=1.0,
        source_subject=f"{author} - {title}",
        nzb="<nzb>large payload</nzb>",
        fingerprint=release_id,
        wanted_key=f"{author.casefold()}|{title.casefold()}",
        download_status=download_status,
        import_status=import_status,
        posted_at=datetime(2026, 1, day, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("limit", "offset", "message"),
    [(0, 0, "limit"), (101, 0, "limit"), (50, -1, "offset")],
)
def test_search_query_rejects_unbounded_pagination(limit, offset, message):
    with pytest.raises(ValueError, match=message):
        ReleaseSearchQuery(limit=limit, offset=offset)


def test_search_page_returns_bounded_summary_page_and_stable_tie_breaker(repository):
    page = repository.search_page(
        ReleaseSearchQuery(q="project", limit=1, offset=1, sort="title", order="asc")
    )

    assert page.total == 2
    assert page.limit == 1
    assert page.offset == 1
    assert [item.id for item in page.results] == ["release-2"]
    assert not hasattr(page.results[0], "nzb")
    assert not hasattr(page.results[0], "source_subject")


@pytest.mark.parametrize(
    ("filters", "expected_ids"),
    [
        ({"format": "mp3"}, ["release-2"]),
        ({"download_status": "completed"}, ["release-2", "release-3"]),
        ({"import_status": "imported"}, ["release-3"]),
        ({"format": "m4b", "download_status": "completed", "import_status": "imported"}, ["release-3"]),
    ],
)
def test_search_page_applies_release_filters(repository, filters, expected_ids):
    page = repository.search_page(ReleaseSearchQuery(sort="posted_at", order="asc", **filters))

    assert page.total == len(expected_ids)
    assert [item.id for item in page.results] == expected_ids


def test_search_page_sorts_descending_with_stable_id_tie_breaker(repository):
    page = repository.search_page(ReleaseSearchQuery(q="project", sort="title", order="desc"))

    assert [item.id for item in page.results] == ["release-2", "release-1"]
