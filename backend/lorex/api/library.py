from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("/books")
def list_books(request: Request) -> dict:
    books = request.app.state.container.library.all()
    return {"count": len(books), "books": [asdict(book) for book in books]}
