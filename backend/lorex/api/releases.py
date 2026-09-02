from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from lorex.domain import ArticleHeader, DownloadJob
from lorex.services.indexing import index_headers

router = APIRouter(prefix="/api", tags=["releases"])


class HeaderInput(BaseModel):
    message_id: str
    subject: str
    bytes: int
    group: str = "alt.binaries.audiobooks"


class MockIndexRequest(BaseModel):
    headers: list[HeaderInput]


@router.post("/index/mock")
def mock_index(payload: MockIndexRequest, request: Request) -> dict:
    container = request.app.state.container
    headers = [ArticleHeader(**item.model_dump()) for item in payload.headers]
    releases = index_headers(headers, container.releases)
    return {"indexed": len(releases), "releases": [asdict(item) for item in releases]}


@router.get("/releases/search")
def search_releases(q: str = "", request: Request = None) -> dict:
    container = request.app.state.container
    results = container.releases.search(q)
    return {"count": len(results), "results": [asdict(item) for item in results]}


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
