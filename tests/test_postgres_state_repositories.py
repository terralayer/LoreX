from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from lorex.db import create_engine_from_url, session_factory
from lorex.domain import DownloadJob, LibraryBook
from lorex.main import AppContainer
from lorex.postgres_repository import PostgresJobRepository, PostgresLibraryRepository, PostgresReleaseRepository


@pytest.fixture()
def sessions():
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE download_jobs, library_books RESTART IDENTITY CASCADE"))
    factory = session_factory(engine)
    yield factory
    engine.dispose()


def test_library_books_survive_repository_recreation(sessions):
    first = PostgresLibraryRepository(sessions)
    book = LibraryBook(
        id="book-1",
        title="Project Hail Mary",
        author="Andy Weir",
        narrator="Ray Porter",
        format="m4b",
        path="/library/Andy Weir/Project Hail Mary/Project Hail Mary.m4b",
        size=123456,
    )
    first.add(book)

    second = PostgresLibraryRepository(sessions)
    assert second.all() == [book]


def test_download_jobs_survive_recreation_and_claim_fifo(sessions):
    first = PostgresJobRepository(sessions)
    first.add(DownloadJob(id="job-1", release_id="release-1"))
    first.add(DownloadJob(id="job-2", release_id="release-2"))

    second = PostgresJobRepository(sessions)
    assert second.pop_next() == DownloadJob(id="job-1", release_id="release-1", status="downloading")
    assert second.get("job-1") == DownloadJob(id="job-1", release_id="release-1", status="downloading")
    assert second.pop_next() == DownloadJob(id="job-2", release_id="release-2", status="downloading")
    assert second.get("job-2") == DownloadJob(id="job-2", release_id="release-2", status="downloading")
    assert second.pop_next() is None


def test_app_container_uses_postgres_when_database_url_is_configured():
    container = AppContainer.build(os.environ["LOREX_DATABASE_URL"])

    assert isinstance(container.releases, PostgresReleaseRepository)
    assert isinstance(container.jobs, PostgresJobRepository)
    assert isinstance(container.library, PostgresLibraryRepository)
