from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from lorex.domain import ArticleHeader, DownloadJob
from lorex.indexer.nzb import get_or_build_nzb
from lorex.services.indexing import index_headers
from lorex.search import DownloadStatus, ImportStatus, ReleaseFormat, ReleaseSearchQuery, ReleaseSort, SortOrder

router = APIRouter(prefix="/api", tags=["releases"])


class HeaderInput(BaseModel):
    message_id: str
    subject: str
    bytes: int
    group: str = "alt.binaries.audiobooks"


class MockIndexRequest(BaseModel):
    headers: list[HeaderInput]


class ReleaseSummaryResponse(BaseModel):
    id: str
    title: str
    author: str
    narrator: str | None
    format: str
    size: int
    completion: float
    download_status: str | None
    import_status: str | None
    posted_at: datetime | None


class ReleaseSearchResponse(BaseModel):
    total: int
    limit: int
    offset: int
    results: list[ReleaseSummaryResponse]


class ReleaseDetailResponse(BaseModel):
    id: str
    title: str
    author: str
    narrator: str | None
    format: str
    size: int
    completion: float
    nzb: str
    source_subject: str


@router.post("/index/mock")
def mock_index(payload: MockIndexRequest, request: Request) -> dict:
    container = request.app.state.container
    headers = [ArticleHeader(**item.model_dump()) for item in payload.headers]
    releases = index_headers(headers, container.releases)
    return {"indexed": len(releases), "releases": [asdict(item) for item in releases]}


@router.get("/releases/search", response_model=ReleaseSearchResponse)
def search_releases(
    request: Request,
    q: str = "",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: ReleaseSort = "title",
    order: SortOrder = "asc",
    format: ReleaseFormat | None = None,
    download_status: DownloadStatus | None = None,
    import_status: ImportStatus | None = None,
) -> ReleaseSearchResponse:
    container = request.app.state.container
    page = container.releases.search_page(
        ReleaseSearchQuery(
            q=q,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
            format=format,
            download_status=download_status,
            import_status=import_status,
        )
    )
    return ReleaseSearchResponse(**asdict(page))


@router.get("/releases/{release_id}", response_model=ReleaseDetailResponse)
def release_detail(release_id: str, request: Request) -> ReleaseDetailResponse:
    release = request.app.state.container.releases.get(release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")
    return ReleaseDetailResponse(**asdict(release))


@router.get("/releases/{release_id}/nzb")
def release_nzb(release_id: str, request: Request) -> Response:
    container = request.app.state.container
    try:
        payload = get_or_build_nzb(release_id, container.releases)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Release NZB not found") from exc
    return Response(content=payload, media_type="application/x-nzb")


@router.post("/releases/{release_id}/grab")
def grab_release(release_id: str, request: Request) -> dict:
    container = request.app.state.container
    if container.releases.get(release_id) is None:
        raise HTTPException(status_code=404, detail="Release not found")
    job = DownloadJob(id=uuid4().hex[:12], release_id=release_id)
    container.jobs.add(job)
    return asdict(job)


@router.post("/downloads/process-next")
def process_next_download(request: Request) -> dict:
    container = request.app.state.container
    job = container.jobs.pop_next()
    if job is None:
        raise HTTPException(status_code=404, detail="No queued downloads")
    release = container.releases.get(job.release_id)
    if release is None:
        raise HTTPException(status_code=409, detail="Queued release no longer exists")
    result = container.downloader.download(release)
    book = container.importer.import_download(result)
    return {"job_id": job.id, "status": "completed", "book": asdict(book)}
