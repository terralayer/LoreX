from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest

from lorex.db import create_engine_from_url, session_factory
from lorex.domain import DownloadJob
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


def test_claim_is_non_destructive_and_fifo(repository: PostgresJobRepository) -> None:
    first = DownloadJob(id=f"job-{uuid4()}", release_id="release-1")
    second = DownloadJob(id=f"job-{uuid4()}", release_id="release-2")
    repository.add(first)
    repository.add(second)

    claimed = repository.claim_next("worker-a")

    assert claimed is not None
    assert claimed.id == first.id
    assert repository.get(first.id).status == "downloading"
    assert repository.get(second.id).status == "queued"


def test_two_workers_cannot_claim_same_job(repository: PostgresJobRepository) -> None:
    job = DownloadJob(id=f"job-{uuid4()}", release_id="release-1")
    repository.add(job)

    first = repository.claim_next("worker-a")
    second = repository.claim_next("worker-b")

    assert first is not None
    assert second is None


def test_terminal_transitions_are_durable(repository: PostgresJobRepository) -> None:
    completed = DownloadJob(id=f"job-{uuid4()}", release_id="release-1")
    failed = DownloadJob(id=f"job-{uuid4()}", release_id="release-2")
    repository.add(completed)
    repository.add(failed)
    repository.claim_next("worker-a")
    repository.mark_completed(completed.id)
    repository.claim_next("worker-a")
    repository.mark_failed(failed.id)

    assert repository.get(completed.id).status == "completed"
    assert repository.get(failed.id).status == "failed"


def test_recover_stale_returns_only_old_downloading_jobs_to_queue(repository: PostgresJobRepository) -> None:
    job = DownloadJob(id=f"job-{uuid4()}", release_id="release-1")
    repository.add(job)
    repository.claim_next("worker-a")

    recovered = repository.recover_stale(datetime.now(UTC) + timedelta(seconds=1))

    assert recovered == 1
    assert repository.get(job.id).status == "queued"
