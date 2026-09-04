from __future__ import annotations

from types import SimpleNamespace

from lorex.domain import DownloadJob, DownloadResult, IndexedRelease, LibraryBook
from lorex.services.download_jobs import process_next_download, queue_release


RELEASE = IndexedRelease(
    id="release-1",
    title="Synthetic Book",
    author="Synthetic Author",
    narrator=None,
    format="m4b",
    size=8,
    completion=1.0,
    nzb="",
    source_subject="Synthetic Author - Synthetic Book.m4b [1/1]",
)


class Releases:
    def get(self, release_id):
        return RELEASE if release_id == RELEASE.id else None

    def get_articles(self, release_id):
        return ()


class Jobs:
    def __init__(self):
        self.jobs = []
        self.failed = []
        self.completed = []

    def find_active_for_release(self, release_id):
        return next((job for job in self.jobs if job.release_id == release_id and job.status in {"queued", "downloading"}), None)

    def add(self, job):
        self.jobs.append(job)
        return job

    def claim_next(self, worker_id):
        for index, job in enumerate(self.jobs):
            if job.status == "queued":
                claimed = DownloadJob(job.id, job.release_id, "downloading")
                self.jobs[index] = claimed
                return claimed
        return None

    def is_cancel_requested(self, job_id):
        return False

    def set_runtime_status(self, job_id, status):
        for index, job in enumerate(self.jobs):
            if job.id == job_id:
                self.jobs[index] = DownloadJob(job.id, job.release_id, status)

    def mark_completed(self, job_id):
        self.completed.append(job_id)

    def mark_failed(self, job_id, error=None):
        self.failed.append((job_id, error))


class Runtime:
    def __init__(self):
        self.activity = []

    def append_activity(self, kind, message, *, entity_id=None, detail=None):
        self.activity.append((kind, message, entity_id, detail))


class Downloader:
    def download(self, release):
        return DownloadResult(
            release_id=release.id,
            title=release.title,
            author=release.author,
            narrator=release.narrator,
            format=release.format,
            file_name="synthetic.m4b",
            size=release.size,
        )


class Importer:
    def import_download(self, result):
        return LibraryBook(
            id=result.release_id,
            title=result.title,
            author=result.author,
            narrator=result.narrator,
            format=result.format,
            path=f"/library/{result.file_name}",
            size=result.size,
        )


def container():
    return SimpleNamespace(
        releases=Releases(),
        jobs=Jobs(),
        runtime=Runtime(),
        downloader=Downloader(),
        importer=Importer(),
        mock_api_enabled=True,
        mock_release_ids={RELEASE.id},
        mock_downloader=Downloader(),
        nntp_providers=None,
        credential_key_available=False,
    )


def test_queue_release_is_idempotent_for_active_job() -> None:
    state = container()

    first = queue_release(state, RELEASE.id)
    second = queue_release(state, RELEASE.id)

    assert first.id == second.id
    assert len(state.jobs.jobs) == 1


def test_process_next_download_completes_without_manual_pipeline_steps() -> None:
    state = container()
    job = queue_release(state, RELEASE.id)

    result = process_next_download(state, worker_id="test-worker")

    assert result is not None
    assert result.job_id == job.id
    assert result.status == "completed"
    assert result.book is not None
    assert state.jobs.completed == [job.id]
    assert any(event[0] == "download" for event in state.runtime.activity)


def test_process_next_download_persists_failure_and_does_not_raise() -> None:
    state = container()
    queue_release(state, RELEASE.id)

    class BrokenDownloader:
        def download(self, release):
            raise RuntimeError("synthetic provider failure")

    state.mock_downloader = BrokenDownloader()
    result = process_next_download(state, worker_id="test-worker")

    assert result is not None
    assert result.status == "failed"
    assert "synthetic provider failure" in (result.error or "")
    assert state.jobs.failed and state.jobs.failed[0][0] == result.job_id
