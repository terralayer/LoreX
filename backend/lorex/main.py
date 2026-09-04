from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from sqlalchemy import Engine

from lorex.api.library import router as library_router
from lorex.api.nntp_settings import router as nntp_settings_router
from lorex.api.releases import router as releases_router
from lorex.db import create_engine_from_url, database_url_from_env, session_factory
from lorex.downloader.mock import MockDownloader
from lorex.library.importer import LibraryImporter
from lorex.nntp.repository import PostgresNntpProviderRepository
from lorex.read_repository import (
    ResponsivePostgresJobRepository,
    ResponsivePostgresLibraryRepository,
    ResponsivePostgresReleaseRepository,
)
from lorex.repository import JobRepository, LibraryRepository, ReleaseRepository
from lorex.security.credentials import credential_cipher_from_env


@dataclass(slots=True)
class AppContainer:
    releases: Any
    jobs: Any
    library: Any
    downloader: Any
    importer: LibraryImporter
    engine: Engine | None = None
    nntp_providers: PostgresNntpProviderRepository | None = None
    credential_key_available: bool = False

    @classmethod
    def build(cls, database_url: str | None = None) -> "AppContainer":
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
                # Production PostgreSQL mode builds the live NNTP downloader lazily
                # per operation so an unconfigured provider cannot prevent boot.
                downloader=None,
                importer=LibraryImporter(library),
                engine=engine,
                nntp_providers=PostgresNntpProviderRepository(sessions, cipher),
                credential_key_available=cipher is not None,
            )

        library = LibraryRepository()
        return cls(
            releases=ReleaseRepository(),
            jobs=JobRepository(),
            library=library,
            downloader=MockDownloader(),
            importer=LibraryImporter(library),
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
    return application


app = create_app()
