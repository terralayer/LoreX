from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import Engine

from lorex.api.activity import router as activity_router
from lorex.api.downloads import router as downloads_router
from lorex.api.indexer import router as indexer_router
from lorex.api.library import router as library_router
from lorex.api.nntp_settings import router as nntp_settings_router
from lorex.api.releases import router as releases_router
from lorex.api.system import router as system_router
from lorex.db import create_engine_from_url, database_url_from_env, session_factory
from lorex.downloader.mock import MockDownloader
from lorex.library.importer import LibraryImporter
from lorex.nntp.repository import PostgresNntpProviderRepository
from lorex.postprocess import PostProcessor
from lorex.read_repository import (
    ResponsivePostgresJobRepository,
    ResponsivePostgresLibraryRepository,
    ResponsivePostgresReleaseRepository,
)
from lorex.repository import JobRepository, LibraryRepository, ReleaseRepository
from lorex.runtime_repository import PostgresRuntimeRepository
from lorex.security.credentials import credential_cipher_from_env


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class AppContainer:
    releases: Any
    jobs: Any
    library: Any
    downloader: Any
    importer: LibraryImporter
    postprocessor: PostProcessor
    engine: Engine | None = None
    nntp_providers: PostgresNntpProviderRepository | None = None
    runtime: PostgresRuntimeRepository | None = None
    credential_key_available: bool = False
    mock_api_enabled: bool = False
    nntp_client_factory: Any | None = None
    download_root: str = "/downloads"
    mock_downloader: MockDownloader = field(default_factory=MockDownloader)
    mock_release_ids: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, database_url: str | None = None) -> "AppContainer":
        mock_api_enabled = _env_enabled("LOREX_ENABLE_MOCK_API")
        if database_url:
            engine = create_engine_from_url(database_url)
            sessions = session_factory(engine)
            library = ResponsivePostgresLibraryRepository(sessions)
            jobs = ResponsivePostgresJobRepository(sessions)
            cipher = credential_cipher_from_env()
            return cls(
                releases=ResponsivePostgresReleaseRepository(sessions),
                jobs=jobs,
                library=library,
                downloader=None,
                importer=LibraryImporter(library),
                postprocessor=PostProcessor(),
                engine=engine,
                nntp_providers=PostgresNntpProviderRepository(sessions, cipher),
                runtime=PostgresRuntimeRepository(sessions),
                credential_key_available=cipher is not None,
                mock_api_enabled=mock_api_enabled,
            )

        library = LibraryRepository()
        mock_downloader = MockDownloader()
        return cls(
            releases=ReleaseRepository(),
            jobs=JobRepository(),
            library=library,
            downloader=mock_downloader if mock_api_enabled else None,
            importer=LibraryImporter(library),
            postprocessor=PostProcessor(),
            mock_api_enabled=mock_api_enabled,
            mock_downloader=mock_downloader,
        )

    def close(self) -> None:
        if self.engine is not None:
            self.engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = AppContainer.build(database_url_from_env())
    app.state.container = container
    try:
        yield
    finally:
        container.close()


def create_app() -> FastAPI:
    application = FastAPI(title="LoreX", version="0.1.1 alpha", lifespan=lifespan)

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": "LoreX"}

    application.include_router(releases_router)
    application.include_router(library_router)
    application.include_router(nntp_settings_router)
    application.include_router(indexer_router)
    application.include_router(downloads_router)
    application.include_router(activity_router)
    application.include_router(system_router)

    frontend_dist = Path("frontend-dist")
    frontend_index = frontend_dist / "index.html"
    if frontend_index.is_file():
        frontend_root = frontend_dist.resolve()

        @application.get("/{frontend_path:path}", include_in_schema=False)
        def serve_frontend(frontend_path: str):
            if frontend_path == "api" or frontend_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")

            requested = (frontend_dist / frontend_path).resolve()
            if requested.is_relative_to(frontend_root) and requested.is_file():
                return FileResponse(requested)
            return FileResponse(frontend_index)

    return application


app = create_app()
