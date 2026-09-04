from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from lorex.search import LibrarySearchQuery, LibrarySort, SortOrder

router = APIRouter(tags=["library"])


class DashboardSummaryResponse(BaseModel):
    total_releases: int
    download_statuses: dict[str, int]
    import_statuses: dict[str, int]


class LibrarySummaryResponse(BaseModel):
    id: str
    title: str
    author: str
    narrator: str | None
    format: str
    size: int


class LibraryPageResponse(BaseModel):
    total: int
    limit: int
    offset: int
    results: list[LibrarySummaryResponse]


class AppDashboardResponse(BaseModel):
    library_books: int
    total_releases: int
    active_downloads: int
    queued_downloads: int


@router.get("/api/library/books", response_model=LibraryPageResponse)
def list_books(
    request: Request,
    q: str = "",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: LibrarySort = "title",
    order: SortOrder = "asc",
) -> LibraryPageResponse:
    page = request.app.state.container.library.search_page(
        LibrarySearchQuery(q=q, limit=limit, offset=offset, sort=sort, order=order)
    )
    return LibraryPageResponse(**asdict(page))


@router.get("/api/library/dashboard", response_model=DashboardSummaryResponse)
def dashboard_summary(request: Request) -> DashboardSummaryResponse:
    summary = request.app.state.container.releases.dashboard_summary()
    return DashboardSummaryResponse(**asdict(summary))


@router.get("/api/dashboard", response_model=AppDashboardResponse)
def app_dashboard(request: Request) -> AppDashboardResponse:
    container = request.app.state.container
    release_summary = container.releases.dashboard_summary()
    job_counts = container.jobs.status_counts()
    return AppDashboardResponse(
        library_books=container.library.count(),
        total_releases=release_summary.total_releases,
        active_downloads=job_counts.get("downloading", 0),
        queued_downloads=job_counts.get("queued", 0),
    )
