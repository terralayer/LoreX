from __future__ import annotations

import gzip
import os
import re
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

from benchmarks.metrics import measure_samples
from lorex.db import create_engine_from_url
from lorex.main import create_app

_ENTRY_SCRIPT = re.compile(r'<script[^>]+src=["\']/?([^"\']+\.js)["\'][^>]*>', re.IGNORECASE)


def measure_entry_script(frontend_dist: str | Path) -> dict[str, Any]:
    root = Path(frontend_dist)
    index = root / "index.html"
    if not index.is_file():
        raise FileNotFoundError(index)
    match = _ENTRY_SCRIPT.search(index.read_text(encoding="utf-8"))
    if match is None:
        raise RuntimeError("frontend index.html does not reference an entry JavaScript module")

    relative = match.group(1).lstrip("/")
    entry = root / relative
    if not entry.is_file():
        raise FileNotFoundError(entry)
    data = entry.read_bytes()
    js_files = sorted(root.rglob("*.js"))
    return {
        "path": relative,
        "raw_bytes": len(data),
        "gzip_bytes": len(gzip.compress(data, compresslevel=9, mtime=0)),
        "total_js_files": len(js_files),
        "lazy_js_files": max(0, len(js_files) - 1),
    }


def _database_url(explicit: str | None = None) -> str:
    value = explicit or os.environ.get("LOREX_DATABASE_URL")
    if not value:
        raise RuntimeError("LOREX_DATABASE_URL is required for PR8 API benchmarks")
    return value


def _seed_ui_data(database_url: str, release_scale: int, library_scale: int, job_scale: int) -> None:
    engine = create_engine_from_url(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE release_articles, indexer_checkpoints, releases, "
                    "download_articles, provider_health, download_jobs, import_jobs, "
                    "library_books RESTART IDENTITY CASCADE"
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO releases (
                        id, title, normalized_title, author, normalized_author,
                        narrator, format, size, completion, source_subject, nzb,
                        fingerprint, wanted_key, download_status, import_status, posted_at
                    )
                    SELECT
                        'ui-release-' || n,
                        'UI Benchmark Audiobook ' || n,
                        'ui benchmark audiobook ' || n,
                        'UI Benchmark Author ' || (n % 1000),
                        'ui benchmark author ' || (n % 1000),
                        'UI Benchmark Narrator ' || (n % 100),
                        CASE WHEN n % 2 = 0 THEN 'm4b' ELSE 'mp3' END,
                        100000000 + n,
                        1.0,
                        'UI Benchmark Subject ' || n,
                        '',
                        'ui-fingerprint-' || n,
                        'ui-wanted-' || n,
                        CASE WHEN n % 5 = 0 THEN 'downloading' WHEN n % 5 = 1 THEN 'queued' ELSE 'completed' END,
                        CASE WHEN n % 7 = 0 THEN 'importing' WHEN n % 7 = 1 THEN 'pending' ELSE 'imported' END,
                        TIMESTAMPTZ '2026-01-01 00:00:00+00' + n * INTERVAL '1 second'
                    FROM generate_series(1, :scale) AS generated(n)
                    """
                ),
                {"scale": release_scale},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO library_books (id, title, author, narrator, format, path, size)
                    SELECT
                        'ui-book-' || lpad(n::text, 7, '0'),
                        'Library Book ' || lpad(n::text, 7, '0'),
                        'Library Author ' || lpad((n % 1000)::text, 4, '0'),
                        'Library Narrator ' || lpad((n % 100)::text, 3, '0'),
                        CASE WHEN n % 2 = 0 THEN 'm4b' ELSE 'mp3' END,
                        '/library/ui/' || n || '.m4b',
                        200000000 + n
                    FROM generate_series(1, :scale) AS generated(n)
                    """
                ),
                {"scale": library_scale},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO download_jobs (id, release_id, status, bytes_completed, articles_completed, updated_at)
                    SELECT
                        'ui-job-' || n,
                        'ui-release-' || (((n - 1) % :release_scale) + 1),
                        CASE WHEN n % 3 = 0 THEN 'downloading' WHEN n % 3 = 1 THEN 'queued' ELSE 'completed' END,
                        0,
                        0,
                        now()
                    FROM generate_series(1, :scale) AS generated(n)
                    """
                ),
                {"scale": job_scale, "release_scale": release_scale},
            )
            connection.execute(text("ANALYZE releases"))
            connection.execute(text("ANALYZE library_books"))
            connection.execute(text("ANALYZE download_jobs"))
    finally:
        engine.dispose()


def run_ui_api_benchmarks(
    *,
    frontend_dist: str | Path,
    database_url: str | None = None,
    release_scale: int = 100_000,
    library_scale: int = 100_000,
    job_scale: int = 1_000,
    samples: int = 20,
) -> dict[str, Any]:
    url = _database_url(database_url)
    _seed_ui_data(url, release_scale, library_scale, job_scale)
    app = create_app()

    with TestClient(app) as client:
        def dashboard_request() -> int:
            response = client.get("/api/dashboard")
            response.raise_for_status()
            payload = response.json()
            if payload["library_books"] != library_scale or payload["total_releases"] != release_scale:
                raise RuntimeError("dashboard aggregate returned incorrect seeded counts")
            return len(response.content)

        dashboard_timing = measure_samples("pr8_dashboard_api", dashboard_request, samples=samples, warmups=3)
        dashboard_response = client.get("/api/dashboard")

        page_offset = min(50_000, max(0, library_scale - 50))

        def library_request() -> int:
            response = client.get(
                "/api/library/books",
                params={"limit": 50, "offset": page_offset, "sort": "title", "order": "asc"},
            )
            response.raise_for_status()
            payload = response.json()
            if len(payload["results"]) > 50 or payload["limit"] != 50:
                raise RuntimeError("library API returned an oversized page")
            return len(payload["results"])

        library_timing = measure_samples("pr8_library_page_api", library_request, samples=samples, warmups=3)
        library_response = client.get(
            "/api/library/books",
            params={"limit": 50, "offset": page_offset, "sort": "title", "order": "asc"},
        )
        library_payload = library_response.json()

    return {
        "product_version": "0.1.1 alpha",
        "release_scale": release_scale,
        "library_scale": library_scale,
        "job_scale": job_scale,
        "samples": samples,
        "dashboard": {
            "p50_ms": dashboard_timing.p50_ms,
            "p95_ms": dashboard_timing.p95_ms,
            "mean_ms": dashboard_timing.mean_ms,
            "peak_python_mb": dashboard_timing.peak_python_mb,
            "response_bytes": len(dashboard_response.content),
        },
        "library_page": {
            "p50_ms": library_timing.p50_ms,
            "p95_ms": library_timing.p95_ms,
            "mean_ms": library_timing.mean_ms,
            "peak_python_mb": library_timing.peak_python_mb,
            "requested_limit": 50,
            "result_count": len(library_payload["results"]),
            "response_bytes": len(library_response.content),
            "offset": page_offset,
        },
        "frontend_entry": measure_entry_script(frontend_dist),
    }
