from __future__ import annotations

from lorex.domain import DownloadResult, ImportJob
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
        self.seen: list[tuple[str, str]] = []

    def process(self, job: ImportJob, result: DownloadResult):
        self.seen.append((job.id, result.release_id))
        if self.fail:
            raise RuntimeError("boom")
        return object()


def _result(release_id: str) -> DownloadResult:
    return DownloadResult(release_id, "Book", "Author", None, "m4b", "Book.m4b", 5)


def test_no_import_work_returns_false_without_loading_result() -> None:
    loads: list[str] = []
    assert run_import_once(Repository(None), Pipeline(), lambda rid: loads.append(rid), "worker-a") is False
    assert loads == []


def test_worker_loads_release_result_and_processes_exactly_one_claimed_job() -> None:
    job = ImportJob("i1", "r1", "/downloads/1")
    pipeline = Pipeline()
    assert run_import_once(Repository(job), pipeline, _result, "worker-a") is True
    assert pipeline.seen == [("i1", "r1")]


def test_worker_failure_is_durable() -> None:
    repository = Repository(ImportJob("i1", "r1", "/downloads/1"))
    assert run_import_once(repository, Pipeline(fail=True), _result, "worker-a") is True
    assert repository.failed == ["i1"]
