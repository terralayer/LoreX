from __future__ import annotations

import random
from hashlib import sha1

from lorex.domain import ArticleHeader, DownloadJob, DownloadResult, IndexedRelease
from lorex.repository import JobRepository, ReleaseRepository


def search_term(seed: int) -> str:
    return f"Benchmark Needle {seed}"


def generate_headers(count: int, seed: int = 1101) -> list[ArticleHeader]:
    if count < 0:
        raise ValueError("count cannot be negative")

    rng = random.Random(seed)
    headers: list[ArticleHeader] = []
    for index in range(count):
        book_index = index // 3
        part = index % 3 + 1
        subject = (
            f"Benchmark Author {book_index:08d} - "
            f"Benchmark Book {book_index:08d} - "
            f"Benchmark Narrator {book_index % 97:03d}.m4b [{part}/3]"
        )
        headers.append(
            ArticleHeader(
                message_id=f"<bench-{seed}-{index:012d}@example.test>",
                subject=subject,
                bytes=rng.randint(8_000_000, 24_000_000),
                group="alt.binaries.audiobooks",
            )
        )
    return headers


def populate_releases(count: int, seed: int = 1101) -> ReleaseRepository:
    if count < 0:
        raise ValueError("count cannot be negative")

    repository = ReleaseRepository()
    for index in range(count):
        title = search_term(seed) if index == count - 1 else f"Benchmark Book {seed}-{index:08d}"
        author = f"Benchmark Author {index % 1000:04d}"
        narrator = f"Benchmark Narrator {index % 97:03d}"
        release_id = sha1(f"release|{seed}|{index}".encode("utf-8")).hexdigest()[:16]
        repository.add(
            IndexedRelease(
                id=release_id,
                title=title,
                author=author,
                narrator=narrator,
                format="m4b",
                size=500_000_000 + (index % 10_000) * 4096,
                completion=1.0,
                nzb="",
                source_subject=f"{author} - {title} - {narrator}.m4b",
            )
        )
    return repository


def populate_jobs(count: int) -> JobRepository:
    if count < 0:
        raise ValueError("count cannot be negative")

    repository = JobRepository()
    for index in range(count):
        repository.add(DownloadJob(id=f"job-{index:08d}", release_id=f"release-{index:08d}"))
    return repository


def generate_download_results(count: int, seed: int = 1101) -> list[DownloadResult]:
    if count < 0:
        raise ValueError("count cannot be negative")

    rng = random.Random(seed)
    results: list[DownloadResult] = []
    for index in range(count):
        title = f"Benchmark Import {seed}-{index:08d}"
        results.append(
            DownloadResult(
                release_id=sha1(f"download|{seed}|{index}".encode("utf-8")).hexdigest()[:16],
                title=title,
                author=f"Benchmark Author {index % 1000:04d}",
                narrator=f"Benchmark Narrator {index % 97:03d}",
                format="m4b",
                file_name=f"{title}.m4b",
                size=rng.randint(250_000_000, 1_500_000_000),
            )
        )
    return results
