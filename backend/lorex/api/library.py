from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/library", tags=["library"])


class DashboardSummaryResponse(BaseModel):
    total_releases: int
    download_statuses: dict[str, int]
    import_statuses: dict[str, int]


@router.get("/books")
def list_books(request: Request) -> dict:
    books = request.app.state.container.library.all()
    return {"count": len(books), "books": [asdict(book) for book in books]}


@router.get("/dashboard", response_model=DashboardSummaryResponse)
def dashboard_summary(request: Request) -> DashboardSummaryResponse:
    summary = request.app.state.container.releases.dashboard_summary()
    return DashboardSummaryResponse(**asdict(summary))
