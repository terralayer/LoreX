from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from benchmarks.datasets import (
    generate_download_results,
    generate_headers,
    populate_jobs,
    populate_releases,
    search_term,
)
from benchmarks.metrics import BenchmarkResult, measure_samples
from lorex.db import create_engine_from_url, session_factory
from lorex.db_models import ReleaseRow
from lorex.downloader.mock import MockDownloader
from lorex.indexer.classifier import classify_audiobook
from lorex.indexer.grouping import group_headers
from lorex.library.importer import LibraryImporter
from lorex.main import create_app
from lorex.postgres_repository import PostgresReleaseRepository
from lorex.repository import LibraryRepository, ReleaseRepository
from lorex.services.indexing import IndexBatch, index_batches

_INDEX_HEADER_BATCH_SIZE = 2048
_INDEX_WRITE_BATCH_SIZE = 512
_INDEX_MAX_PENDING_GROUPS = 4096


def _throughput(operation_count: int, timing: BenchmarkResult) -> float:
    if timing.mean_ms <= 0:
        return 0.0
    return operation_count / (timing.mean_ms / 1000.0)


def _result(
    name: str,
    scale: int,
    unit: str,
    operation_count: int,
    timing: BenchmarkResult,
    note: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "scale": scale,
        "unit": unit,
        "operation_count": operation_count,
        "throughput_per_sec": _throughput(operation_count, timing),
        "timing": timing.to_dict(),
    }
    if note:
        result["note"] = note
    return result


def benchmark_index_headers(scale: int, samples: int) -> dict[str, Any]:
    headers = generate_headers(scale)

    def operation() -> int:
        repository = ReleaseRepository()
        batches = (
            IndexBatch(headers=headers[start : start + _INDEX_HEADER_BATCH_SIZE])
            for start in range(0, len(headers), _INDEX_HEADER_BATCH_SIZE)
        )
        stats = index_batches(
            batches,
            repository,
            batch_size=_INDEX_WRITE_BATCH_SIZE,
            max_pending_groups=_INDEX_MAX_PENDING_GROUPS,
        )
        return stats.releases_indexed

    timing = measure_samples("index_headers", operation, samples=samples, warmups=0)
    return _result(
        "index_headers",
        scale,
        "headers",
        scale,
        timing,
        note=(
            f"Streaming index_batches: header batch {_INDEX_HEADER_BATCH_SIZE}, "
            f"write batch {_INDEX_WRITE_BATCH_SIZE}, max pending groups {_INDEX_MAX_PENDING_GROUPS}."
        ),
    )


def benchmark_group_and_classify(scale: int, samples: int) -> dict[str, Any]:
    headers = generate_headers(scale)

    def operation() -> int:
        candidates = group_headers(headers)
        return sum(1 for candidate in candidates if classify_audiobook(candidate) >= 0.8)

    timing = measure_samples("group_and_classify", operation, samples=samples, warmups=0)
    return _result("group_and_classify", scale, "headers", scale, timing)


def benchmark_release_search(scale: int, samples: int) -> dict[str, Any]:
    seed = 1101
    repository = populate_releases(scale, seed=seed)
    needle = search_term(seed)

    def operation() -> int:
        return len(repository.search(needle))

    timing = measure_samples("release_search", operation, samples=samples, warmups=1)
    return _result("release_search", scale, "releases", scale, timing)


def benchmark_release_search_api(scale: int, samples: int) -> dict[str, Any]:
    seed = 1101
    repository = populate_releases(scale, seed=seed)
    needle = search_term(seed)
    app = create_app()

    with TestClient(app) as client:
        app.state.container.releases = repository

        def operation() -> int:
            response = client.get("/api/releases/search", params={"q": needle})
            response.raise_for_status()
            return response.json()["count"]

        timing = measure_samples("release_search_api", operation, samples=samples, warmups=1)

    return _result(
        "release_search_api",
        scale,
        "releases",
        scale,
        timing,
        note="Representative read API; LoreX does not yet have a dashboard aggregate endpoint.",
    )


def benchmark_queue_roundtrip(scale: int, samples: int) -> dict[str, Any]:
    def operation() -> int:
        repository = populate_jobs(scale)
        processed = 0
        while repository.pop_next() is not None:
            processed += 1
        return processed

    timing = measure_samples("queue_roundtrip", operation, samples=samples, warmups=0)
    return _result(
        "queue_roundtrip",
        scale,
        "jobs",
        scale * 2,
        timing,
        note="Measures deterministic enqueue + FIFO drain. Scale is intentionally bounded because current pop(0) drain is O(n^2).",
    )


def benchmark_mock_downloader(scale: int, samples: int) -> dict[str, Any]:
    releases = list(populate_releases(scale)._items.values())
    downloader = MockDownloader()

    def operation() -> int:
        return sum(1 for release in releases if downloader.download(release).size == release.size)

    timing = measure_samples("mock_downloader", operation, samples=samples, warmups=0)
    return _result("mock_downloader", scale, "downloads", scale, timing)


def benchmark_library_importer(scale: int, samples: int) -> dict[str, Any]:
    downloads = generate_download_results(scale)

    def operation() -> int:
        repository = LibraryRepository()
        importer = LibraryImporter(repository)
        for download in downloads:
            importer.import_download(download)
        return len(repository._items)

    timing = measure_samples("library_importer", operation, samples=samples, warmups=0)
    return _result("library_importer", scale, "imports", scale, timing)


def _postgres_repository() -> tuple[Any, PostgresReleaseRepository]:
    database_url = os.environ.get("LOREX_DATABASE_URL")
    if not database_url:
        raise RuntimeError("LOREX_DATABASE_URL is required for PostgreSQL benchmarks")
    engine = create_engine_from_url(database_url)
    return engine, PostgresReleaseRepository(session_factory(engine))


def _truncate_postgres_releases(engine: Any) -> None:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE release_articles, indexer_checkpoints, releases RESTART IDENTITY CASCADE"))


def benchmark_postgres_bulk_index(scale: int, samples: int) -> dict[str, Any]:
    if samples != 1:
        raise ValueError("postgres_bulk_index uses one measured sample to avoid replaying identical rows")
    releases = list(populate_releases(scale, seed=3303)._items.values())
    records = [(release, ()) for release in releases]
    engine, repository = _postgres_repository()
    _truncate_postgres_releases(engine)

    try:
        def operation() -> int:
            return repository.commit_index_batch(records)

        timing = measure_samples("postgres_bulk_index", operation, samples=1, warmups=0)
    finally:
        engine.dispose()

    return _result(
        "postgres_bulk_index",
        scale,
        "releases",
        scale,
        timing,
        note="Single PostgreSQL transaction using bulk INSERT .. ON CONFLICT; excludes synthetic fixture generation.",
    )


def benchmark_postgres_index_lookup(scale: int, samples: int) -> dict[str, Any]:
    seed = 4404
    releases = list(populate_releases(scale, seed=seed)._items.values())
    needle = " ".join(releases[-1].title.casefold().split())
    engine, repository = _postgres_repository()
    _truncate_postgres_releases(engine)
    repository.commit_index_batch([(release, ()) for release in releases])
    sessions = session_factory(engine)

    try:
        def operation() -> int:
            with sessions() as session:
                return session.execute(
                    select(ReleaseRow.id).where(ReleaseRow.normalized_title == needle)
                ).scalar_one()

        timing = measure_samples("postgres_index_lookup", operation, samples=samples, warmups=1)
    finally:
        engine.dispose()

    return _result(
        "postgres_index_lookup",
        scale,
        "releases",
        1,
        timing,
        note="Exact normalized-title point lookup through ix_releases_normalized_title; PR 4 owns full search API redesign.",
    )


ScenarioFunction = Callable[[int, int], dict[str, Any]]

SCENARIOS: dict[str, ScenarioFunction] = {
    "index_headers": benchmark_index_headers,
    "group_and_classify": benchmark_group_and_classify,
    "release_search": benchmark_release_search,
    "release_search_api": benchmark_release_search_api,
    "queue_roundtrip": benchmark_queue_roundtrip,
    "mock_downloader": benchmark_mock_downloader,
    "library_importer": benchmark_library_importer,
    "postgres_bulk_index": benchmark_postgres_bulk_index,
    "postgres_index_lookup": benchmark_postgres_index_lookup,
}
