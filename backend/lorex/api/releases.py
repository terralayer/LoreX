from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from lorex.domain import ArticleHeader
from lorex.indexer.nzb import get_or_build_nzb
from lorex.services.download_jobs import process_next_download as process_download_job
from lorex.services.download_jobs import queue_release
from lorex.services.indexing import index_headers
from lorex.services.on_demand_search import (
    BookSearchRequest,
    SearchCandidate,
    execute_on_demand_search,
)
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


class OnDemandSearchRequest(BaseModel):
    title: str
    author: str | None = None
    narrator: str | None = None
    series: str | None = None
    series_number: str | int | None = None
    isbn: str | None = None
    asin: str | None = None
    stop_score: int = 95


@router.post("/index/mock")
def mock_index(payload: MockIndexRequest, request: Request) -> dict:
    container = request.app.state.container
    if not getattr(container, "mock_api_enabled", False):
        raise HTTPException(status_code=404, detail="Not Found")
    headers = [ArticleHeader(**item.model_dump()) for item in payload.headers]
    releases = index_headers(headers, container.releases)
    container.mock_release_ids.update(release.id for release in releases)
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


@router.post("/search/on-demand")
def on_demand_search(payload: OnDemandSearchRequest, request: Request) -> dict:
    container = request.app.state.container
    book = BookSearchRequest(
        title=payload.title,
        author=payload.author,
        narrator=payload.narrator,
        series=payload.series,
        series_number=payload.series_number,
        isbn=payload.isbn,
        asin=payload.asin,
    )

    def provider(query: str):
        page = container.releases.search_page(
            ReleaseSearchQuery(q=query, limit=100, offset=0, sort="completion", order="desc")
        )
        candidates: list[SearchCandidate] = []
        for summary in page.results:
            release = container.releases.get(summary.id)
            if release is None:
                continue
            candidates.append(
                SearchCandidate(
                    id=release.id,
                    title=release.title,
                    author=release.author,
                    narrator=release.narrator,
                    format=release.format,
                    size=release.size,
                    completion=release.completion,
                    source_subject=release.source_subject,
                )
            )
        return candidates

    try:
        result = execute_on_demand_search(book, provider, stop_score=payload.stop_score)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "queries": list(result.queries),
        "stopped_early": result.stopped_early,
        "results": [
            {
                "score": item.score,
                "bucket": item.bucket,
                "reasons": list(item.reasons),
                "release": asdict(container.releases.get(item.candidate.id)),
            }
            for item in result.results
            if container.releases.get(item.candidate.id) is not None
        ],
    }


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
    try:
        job = queue_release(request.app.state.container, release_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Release not found") from exc
    return asdict(job)


@router.post("/downloads/process-next")
def process_next_download(request: Request) -> dict:
    result = process_download_job(request.app.state.container, worker_id="compat-api")
    if result is None:
        raise HTTPException(status_code=404, detail="No queued downloads")
    if result.status == "failed":
        detail = result.error or "Download failed"
        if detail.startswith("NntpConfigurationError:"):
            raise HTTPException(status_code=503, detail=detail.partition(":")[2].strip())
        raise HTTPException(status_code=500, detail=detail)
    payload = {"job_id": result.job_id, "status": result.status}
    if result.book is not None:
        payload["book"] = asdict(result.book)
    return payload
