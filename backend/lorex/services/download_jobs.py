from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from lorex.domain import DownloadJob, LibraryBook
from lorex.nntp.errors import NntpConfigurationError
from lorex.nntp.factory import build_live_downloader


@dataclass(frozen=True, slots=True)
class DownloadProcessResult:
    job_id: str
    release_id: str
    status: str
    book: LibraryBook | None = None
    error: str | None = None


def _append_activity(container, kind: str, message: str, *, entity_id: str | None = None, detail: str | None = None) -> None:
    runtime = getattr(container, "runtime", None)
    if runtime is not None:
        runtime.append_activity(kind, message, entity_id=entity_id, detail=detail)


def _safe_error(container, exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    providers = getattr(container, "nntp_providers", None)
    if providers is not None:
        try:
            for provider in providers.list_enabled():
                for secret in (provider.username, provider.password):
                    if secret:
                        message = message.replace(secret, "***")
        except Exception:
            pass
    return message[:4096]


def _mark_failed(jobs, job_id: str, error: str) -> None:
    try:
        jobs.mark_failed(job_id, error)
    except TypeError:
        jobs.mark_failed(job_id)


def _set_status(jobs, job_id: str, status: str) -> None:
    setter = getattr(jobs, "set_runtime_status", None)
    if setter is not None:
        setter(job_id, status)


def _cancel_requested(jobs, job_id: str) -> bool:
    checker = getattr(jobs, "is_cancel_requested", None)
    return bool(checker(job_id)) if checker is not None else False


def _mark_canceled(jobs, job_id: str) -> None:
    marker = getattr(jobs, "mark_canceled", None)
    if marker is not None:
        marker(job_id)
    else:
        _mark_failed(jobs, job_id, "Canceled")


def _is_explicit_mock_release(container, release_id: str) -> bool:
    return bool(
        getattr(container, "mock_api_enabled", False)
        and release_id in getattr(container, "mock_release_ids", set())
    )


def queue_release(container, release_id: str) -> DownloadJob:
    release = container.releases.get(release_id)
    if release is None:
        raise KeyError(release_id)

    find_active = getattr(container.jobs, "find_active_for_release", None)
    if find_active is not None:
        active = find_active(release_id)
        if active is not None:
            return active

    job = DownloadJob(id=uuid4().hex[:12], release_id=release_id)
    container.jobs.add(job)
    _append_activity(
        container,
        "download",
        f"Queued download: {release.title}",
        entity_id=job.id,
    )
    return job


def _download_release(container, job: DownloadJob, release):
    if _is_explicit_mock_release(container, release.id):
        return container.mock_downloader.download(release)

    if getattr(container, "downloader", None) is not None:
        return container.downloader.download(release)

    if getattr(container, "nntp_providers", None) is None:
        raise NntpConfigurationError("NNTP provider storage is unavailable")
    if not getattr(container, "credential_key_available", False):
        raise NntpConfigurationError("LOREX_CREDENTIAL_KEY is required for live NNTP downloads")

    articles = container.releases.get_articles(release.id)
    if not articles:
        raise NntpConfigurationError("Release has no persisted NNTP articles")

    downloader = build_live_downloader(
        container.nntp_providers,
        state=container.jobs,
        root=getattr(container, "download_root", "/downloads"),
        client_factory=getattr(container, "nntp_client_factory", None),
    )
    return downloader.download_job(job, release, articles)


def process_next_download(container, *, worker_id: str) -> DownloadProcessResult | None:
    job = container.jobs.claim_next(worker_id)
    if job is None:
        return None

    release = container.releases.get(job.release_id)
    if release is None:
        error = "Queued release no longer exists"
        _mark_failed(container.jobs, job.id, error)
        _append_activity(container, "download", error, entity_id=job.id, detail=error)
        return DownloadProcessResult(job.id, job.release_id, "failed", error=error)

    if _cancel_requested(container.jobs, job.id):
        _mark_canceled(container.jobs, job.id)
        _append_activity(container, "download", f"Canceled download: {release.title}", entity_id=job.id)
        return DownloadProcessResult(job.id, job.release_id, "canceled")

    try:
        result = _download_release(container, job, release)
        if _cancel_requested(container.jobs, job.id):
            _mark_canceled(container.jobs, job.id)
            _append_activity(container, "download", f"Canceled download: {release.title}", entity_id=job.id)
            return DownloadProcessResult(job.id, job.release_id, "canceled")

        _set_status(container.jobs, job.id, "postprocessing")
        if _is_explicit_mock_release(container, release.id):
            _set_status(container.jobs, job.id, "importing")
            book = container.importer.import_download(result)
        else:
            postprocessor = getattr(container, "postprocessor", None)
            if postprocessor is None:
                raise RuntimeError("Physical post-processing is unavailable")
            processed = postprocessor.process(result)
            _set_status(container.jobs, job.id, "importing")
            book = container.importer.import_file(result, processed.path)

        container.jobs.mark_completed(job.id)
        _append_activity(
            container,
            "download",
            f"Completed download and import: {release.title}",
            entity_id=job.id,
        )
        return DownloadProcessResult(job.id, job.release_id, "completed", book=book)
    except Exception as exc:
        error = _safe_error(container, exc)
        _mark_failed(container.jobs, job.id, error)
        _append_activity(
            container,
            "download",
            f"Download failed: {release.title}",
            entity_id=job.id,
            detail=error,
        )
        return DownloadProcessResult(job.id, job.release_id, "failed", error=error)
