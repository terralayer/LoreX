from __future__ import annotations

import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from time import process_time
from typing import Any

from sqlalchemy import text

from benchmarks.metrics import BenchmarkResult, measure_samples
from lorex.db import create_engine_from_url, session_factory
from lorex.domain import DownloadResult, ImportJob
from lorex.import_repository import PostgresImportJobRepository
from lorex.library.media import MediaProbe
from lorex.library.pipeline import ImportPipeline
from lorex.repository import LibraryRepository

_FIXTURE_BYTES = 64 * 1024


def _throughput(operation_count: int, timing: BenchmarkResult) -> float:
    if timing.mean_ms <= 0:
        return 0.0
    return operation_count / (timing.mean_ms / 1000.0)


def _base_result(name: str, scale: int, unit: str, timing: BenchmarkResult) -> dict[str, Any]:
    return {
        "name": name,
        "scale": scale,
        "unit": unit,
        "operation_count": scale,
        "throughput_per_sec": _throughput(scale, timing),
        "timing": timing.to_dict(),
    }


class _State:
    def set_stage(self, job_id: str, stage: str) -> None:
        return None

    def set_staging_path(self, job_id: str, staging_path: str) -> None:
        return None

    def mark_completed(self, job_id: str, final_path: str) -> None:
        return None

    def mark_failed(self, job_id: str, error: str) -> None:
        raise RuntimeError(error)


def _optimized_preserve_run(scale: int) -> tuple[int, int]:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source_root = root / "downloads"
        library_root = root / "library"
        source_root.mkdir()
        repository = LibraryRepository()
        pipeline = ImportPipeline(
            state=_State(),
            library=repository,
            library_root=library_root,
            verify=lambda path: path.is_file() and path.stat().st_size == _FIXTURE_BYTES,
            needs_repair=lambda path: False,
            repair=lambda path: path,
            needs_extract=lambda path: False,
            extract=lambda path: path,
            probe=lambda path: MediaProbe("mov,mp4,m4a", "aac", True),
            remux=lambda source, target: None,
            transcode=lambda source, target: None,
            tag=lambda path, result: None,
            cleanup=lambda source, staged, destination: None,
        )
        sources: list[Path] = []
        for index in range(scale):
            source = source_root / f"book-{index}.m4b"
            source.write_bytes(b"x" * _FIXTURE_BYTES)
            sources.append(source)
        temp_peak = sum(path.stat().st_size for path in sources)
        for index, source in enumerate(sources):
            result = DownloadResult(
                release_id=f"release-{index}",
                title=f"Book {index}",
                author="Benchmark Author",
                narrator=None,
                format="m4b",
                file_name=source.name,
                size=_FIXTURE_BYTES,
            )
            pipeline.process(ImportJob(f"import-{index}", result.release_id, str(source)), result)
        return len(repository._items), temp_peak


def _legacy_copy_run(scale: int) -> tuple[int, int, int]:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source_root = root / "downloads"
        library_root = root / "library"
        source_root.mkdir()
        library_root.mkdir()
        sources: list[Path] = []
        for index in range(scale):
            source = source_root / f"book-{index}.m4b"
            source.write_bytes(b"x" * _FIXTURE_BYTES)
            sources.append(source)
        copied = 0
        peak = sum(path.stat().st_size for path in sources)
        for index, source in enumerate(sources):
            destination = library_root / f"book-{index}.m4b"
            shutil.copyfile(source, destination)
            copied += source.stat().st_size
            current = sum(path.stat().st_size for path in sources if path.exists()) + sum(
                path.stat().st_size for path in library_root.iterdir()
            )
            peak = max(peak, current)
        for source in sources:
            source.unlink()
        return scale, copied, peak


def benchmark_import_media_pipeline(scale: int, samples: int) -> dict[str, Any]:
    timing = measure_samples(
        "import_media_pipeline",
        lambda: _optimized_preserve_run(scale)[0],
        samples=samples,
        warmups=0,
    )
    legacy_timing = measure_samples(
        "legacy_import_copy",
        lambda: _legacy_copy_run(scale)[0],
        samples=samples,
        warmups=0,
    )

    cpu_started = process_time()
    _, temp_peak = _optimized_preserve_run(scale)
    cpu_ms = (process_time() - cpu_started) * 1000.0
    legacy_cpu_started = process_time()
    _, legacy_bytes_copied, legacy_temp_peak = _legacy_copy_run(scale)
    legacy_cpu_ms = (process_time() - legacy_cpu_started) * 1000.0

    result = _base_result("import_media_pipeline", scale, "imports", timing)
    result.update(
        {
            "cpu_ms": cpu_ms,
            "temp_bytes_peak": temp_peak,
            "bytes_copied": 0,
            "actions": {"preserve": scale, "remux": 0, "transcode": 0},
            "legacy_copy": {
                "p50_ms": legacy_timing.p50_ms,
                "p95_ms": legacy_timing.p95_ms,
                "cpu_ms": legacy_cpu_ms,
                "temp_bytes_peak": legacy_temp_peak,
                "bytes_copied": legacy_bytes_copied,
            },
            "note": "Valid M4B preserve path compared with benchmark-only copy-then-delete behavior; same-filesystem promotion uses atomic rename and zero payload copies.",
        }
    )
    return result


def benchmark_postgres_import_queue_claim(scale: int, samples: int) -> dict[str, Any]:
    if samples != 1:
        raise ValueError("postgres_import_queue_claim uses one measured drain sample")
    database_url = os.environ.get("LOREX_DATABASE_URL")
    if not database_url:
        raise RuntimeError("LOREX_DATABASE_URL is required for PostgreSQL benchmarks")
    engine = create_engine_from_url(database_url)
    repository = PostgresImportJobRepository(session_factory(engine))
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE import_jobs RESTART IDENTITY CASCADE"))
        connection.execute(
            text(
                """
                INSERT INTO import_jobs (id, release_id, status, source_path, stage, updated_at)
                SELECT 'import-' || n, 'release-' || n, 'queued', '/downloads/' || n, 'verify', now()
                FROM generate_series(1, :scale) AS generated(n)
                """
            ),
            {"scale": scale},
        )

    claimed: list[str] = []
    try:
        def operation() -> int:
            while True:
                job = repository.claim_next("benchmark")
                if job is None:
                    break
                claimed.append(job.release_id)
                repository.mark_completed(job.id, final_path=f"/library/{job.id}.m4b")
            return len(claimed)

        timing = measure_samples("postgres_import_queue_claim", operation, samples=1, warmups=0)
    finally:
        engine.dispose()

    result = _base_result("postgres_import_queue_claim", scale, "jobs", timing)
    result["oldest_first"] = claimed == [f"release-{index}" for index in range(1, scale + 1)]
    result["note"] = "Fixture insert excluded; measures durable oldest-first SKIP LOCKED import claims and terminal transitions."
    return result


PR6_SCENARIOS = {
    "import_media_pipeline": benchmark_import_media_pipeline,
    "postgres_import_queue_claim": benchmark_postgres_import_queue_claim,
}
