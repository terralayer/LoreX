from __future__ import annotations

from lorex.domain import DownloadJob
from lorex.repository import JobRepository


def test_pop_next_compatibility_wrapper_claims_without_linear_list_shift() -> None:
    repository = JobRepository()
    repository.add(DownloadJob("job-1", "release-1"))

    job = repository.pop_next()

    assert job is not None
    assert job.id == "job-1"
