from __future__ import annotations

from lorex.domain import DownloadJob
from lorex.repository import JobRepository


def test_job_progress_accumulates_without_changing_terminal_state() -> None:
    repository = JobRepository()
    repository.add(DownloadJob("job-1", "release-1"))
    repository.claim_next("worker-a")

    repository.persist_job_progress("job-1", bytes_delta=100, articles_delta=1)
    repository.persist_job_progress("job-1", bytes_delta=50, articles_delta=0)

    snapshot = repository.progress("job-1")
    assert snapshot == (150, 1)
