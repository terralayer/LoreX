from __future__ import annotations

from lorex.domain import ImportJob
from lorex.services.importing import run_import_once


class Repository:
    def __init__(self, job: ImportJob | None) -> None:
        self.job = job
        self.failed: list[str] = []

    def claim_next(self, worker_id: str):
        job, self.job = self.job, None
        return job

    def mark_failed(self, job_id: str, error: str) -> None:
        self.failed.append(job_id)


class Pipeline:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.seen: list[str] = []

    def process(self, job, result=None):
        self.seen.append(job.id)
        if self.fail:
            raise RuntimeError("boom")
        return object()


def test_no_import_work_returns_false() -> None:
    assert run_import_once(Repository(None), Pipeline(), "worker-a") is False


def test_worker_processes_exactly_one_claimed_job() -> None:
    job = ImportJob("i1", "r1", "/downloads/1")
    pipeline = Pipeline()
    assert run_import_once(Repository(job), pipeline, "worker-a") is True
    assert pipeline.seen == ["i1"]


def test_worker_failure_is_durable() -> None:
    repository = Repository(ImportJob("i1", "r1", "/downloads/1"))
    assert run_import_once(repository, Pipeline(fail=True), "worker-a") is True
    assert repository.failed == ["i1"]
