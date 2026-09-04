from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/library", tags=["library"])


class DashboardSummaryResponse(BaseModel):
    total_books: int
    total_releases: int
    download_statuses: dict[str, int]
    import_statuses: dict[str, int]


@router.get("/books")
def list_books(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    repository = request.app.state.container.library
    books = repository.page(limit=limit, offset=offset)
    return {
        "total": repository.count(),
        "count": len(books),
        "limit": limit,
        "offset": offset,
        "books": [asdict(book) for book in books],
    }


@router.get("/dashboard", response_model=DashboardSummaryResponse)
def dashboard_summary(request: Request) -> DashboardSummaryResponse:
    container = request.app.state.container
    summary = asdict(container.releases.dashboard_summary())
    return DashboardSummaryResponse(total_books=container.library.count(), **summary)
