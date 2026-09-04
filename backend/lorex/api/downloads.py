from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


class DownloadJobResponse(BaseModel):
    id: str
    release_id: str
    status: str
    bytes_completed: int = 0
    articles_completed: int = 0
    total_articles: int = 0
    error: str | None = None
    cancel_requested: bool = False
    completed_at: datetime | None = None
    updated_at: datetime | None = None
    title: str | None = None
    author: str | None = None
    release_size: int | None = None


class DownloadListResponse(BaseModel):
    count: int
    jobs: list[DownloadJobResponse]


def _jobs(request: Request):
    jobs = request.app.state.container.jobs
    if not hasattr(jobs, "list_recent"):
        raise HTTPException(status_code=503, detail="Durable download queue is unavailable")
    return jobs


def _response(job) -> DownloadJobResponse:
    if hasattr(job, "bytes_completed"):
        return DownloadJobResponse(
            id=job.id,
            release_id=job.release_id,
            status=job.status,
            bytes_completed=job.bytes_completed,
            articles_completed=job.articles_completed,
            total_articles=job.total_articles,
            error=job.error,
            cancel_requested=job.cancel_requested,
            completed_at=job.completed_at,
            updated_at=job.updated_at,
            title=job.title,
            author=job.author,
            release_size=job.release_size,
        )
    return DownloadJobResponse(id=job.id, release_id=job.release_id, status=job.status)


@router.get("", response_model=DownloadListResponse)
def list_downloads(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
    status: str | None = None,
) -> DownloadListResponse:
    items = _jobs(request).list_recent(limit=limit, status=status)
    return DownloadListResponse(count=len(items), jobs=[_response(item) for item in items])


@router.post("/{job_id}/retry", response_model=DownloadJobResponse)
def retry_download(job_id: str, request: Request) -> DownloadJobResponse:
    job = _jobs(request).retry(job_id)
    if job is None:
        raise HTTPException(status_code=409, detail="Download is not retryable")
    runtime = getattr(request.app.state.container, "runtime", None)
    if runtime is not None:
        runtime.append_activity("download", "Download queued for retry", entity_id=job_id)
    return _response(job)


@router.post("/{job_id}/cancel", response_model=DownloadJobResponse)
def cancel_download(job_id: str, request: Request) -> DownloadJobResponse:
    job = _jobs(request).request_cancel(job_id)
    if job is None:
        raise HTTPException(status_code=409, detail="Download cannot be canceled")
    runtime = getattr(request.app.state.container, "runtime", None)
    if runtime is not None:
        runtime.append_activity("download", "Download cancellation requested", entity_id=job_id)
    return _response(job)
