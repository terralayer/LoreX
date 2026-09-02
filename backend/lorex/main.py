from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from lorex.api.library import router as library_router
from lorex.api.releases import router as releases_router
from lorex.downloader.mock import MockDownloader
from lorex.library.importer import LibraryImporter
from lorex.repository import JobRepository, LibraryRepository, ReleaseRepository


@dataclass(slots=True)
class AppContainer:
    releases: ReleaseRepository
    jobs: JobRepository
    library: LibraryRepository
    downloader: MockDownloader
    importer: LibraryImporter

    @classmethod
    def build(cls) -> "AppContainer":
        library = LibraryRepository()
        return cls(
            releases=ReleaseRepository(),
            jobs=JobRepository(),
            library=library,
            downloader=MockDownloader(),
            importer=LibraryImporter(library),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.container = AppContainer.build()
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="LoreX", version="0.1.1 alpha", lifespan=lifespan)

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": "LoreX"}

    application.include_router(releases_router)
    application.include_router(library_router)
    return application


app = create_app()
