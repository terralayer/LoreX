from __future__ import annotations

import os
from uuid import uuid4

import pytest

from lorex.db import create_engine_from_url, session_factory
from lorex.domain import ArticleHeader, DownloadJob
from lorex.postgres_repository import PostgresJobRepository


@pytest.fixture()
def repository() -> PostgresJobRepository:
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    sessions = session_factory(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("TRUNCATE download_jobs, download_articles RESTART IDENTITY CASCADE")
    try:
        yield PostgresJobRepository(sessions)
    finally:
        engine.dispose()


def test_postgres_completed_articles_are_skipped_on_resume(repository: PostgresJobRepository) -> None:
    job = DownloadJob(id=f"job-{uuid4()}", release_id="release-1")
    repository.add(job)
    articles = [ArticleHeader("<a1>", "one", 100), ArticleHeader("<a2>", "two", 200)]
    repository.ensure_articles(job.id, articles)
    repository.mark_article_started(job.id, "<a1>", "primary")
    repository.mark_article_completed(job.id, "<a1>", "primary", 100)

    pending = repository.pending_articles(job.id, articles)

    assert [article.message_id for article in pending] == ["<a2>"]
