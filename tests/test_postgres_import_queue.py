from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest

from lorex.db import create_engine_from_url, session_factory
from lorex.domain import ImportJob
from lorex.import_repository import PostgresImportJobRepository


@pytest.fixture()
def repository() -> PostgresImportJobRepository:
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    sessions = session_factory(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("TRUNCATE import_jobs RESTART IDENTITY CASCADE")
    try:
        yield PostgresImportJobRepository(sessions)
    finally:
        engine.dispose()


def test_claim_next_is_oldest_first_and_non_destructive(repository: PostgresImportJobRepository) -> None:
    first = ImportJob(f"i-{uuid4()}", "r1", "/downloads/1")
    second = ImportJob(f"i-{uuid4()}", "r2", "/downloads/2")
    repository.add(first)
    repository.add(second)

    claimed = repository.claim_next("worker-a")

    assert claimed is not None and claimed.id == first.id
    assert repository.get(first.id).status == "processing"
    assert repository.get(second.id).status == "queued"


def test_stage_and_terminal_state_are_durable(repository: PostgresImportJobRepository) -> None:
    job = ImportJob(f"i-{uuid4()}", "r1", "/downloads/1")
    repository.add(job)
    repository.claim_next("worker-a")
    repository.set_stage(job.id, "probing")
    assert repository.get(job.id).stage == "probing"
    repository.mark_completed(job.id, final_path="/library/A/B/B.m4b")
    stored = repository.get(job.id)
    assert stored.status == "completed"
    assert stored.stage == "completed"


def test_stale_claim_recovery_preserves_stage(repository: PostgresImportJobRepository) -> None:
    job = ImportJob(f"i-{uuid4()}", "r1", "/downloads/1")
    repository.add(job)
    repository.claim_next("worker-a")
    repository.set_stage(job.id, "extracting")

    recovered = repository.recover_stale(datetime.now(UTC) + timedelta(seconds=1))

    assert recovered == 1
    stored = repository.get(job.id)
    assert stored.status == "queued"
    assert stored.stage == "extracting"
