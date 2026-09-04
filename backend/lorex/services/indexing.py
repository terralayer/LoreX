from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from lorex.domain import ArticleHeader, IndexCheckpoint, IndexedRelease, ReleaseCandidate
from lorex.indexer.classifier import classify_audiobook
from lorex.indexer.grouping import StreamingHeaderGrouper
from lorex.repository import ReleaseRepository

_INDEXABLE_FORMATS = {"m4b", "m4a", "mp3", "flac", "aac", "archive"}


@dataclass(frozen=True, slots=True)
class IndexBatch:
    headers: Iterable[ArticleHeader]
    checkpoint: IndexCheckpoint | None = None


@dataclass(frozen=True, slots=True)
class IndexingStats:
    headers_received: int = 0
    candidates_completed: int = 0
    releases_indexed: int = 0
    releases_rejected: int = 0
    duplicate_releases: int = 0


def _parse_identity(subject: str) -> tuple[str, str, str | None, str]:
    stem, separator, suffix = subject.rpartition(".")
    if separator:
        fmt = suffix.casefold() or "unknown"
        clean = stem.strip() if fmt in _INDEXABLE_FORMATS else subject.strip()
    else:
        fmt = "unknown"
        clean = subject.strip()

    parts = [part.strip() for part in clean.split(" - ") if part.strip()]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2], fmt
    if len(parts) == 2:
        return parts[0], parts[1], None, fmt
    return "Unknown Author", clean, None, fmt


def _release_record(
    candidate: ReleaseCandidate,
    inspect_candidate: Callable[[ReleaseCandidate], None] | None,
) -> tuple[IndexedRelease, tuple[ArticleHeader, ...]] | None:
    if inspect_candidate is not None:
        inspect_candidate(candidate)

    confidence = classify_audiobook(candidate)
    if confidence < 0.8:
        return None

    author, title, narrator, fmt = _parse_identity(candidate.subject_stem)
    release = IndexedRelease(
        id=candidate.id,
        title=title,
        author=author,
        narrator=narrator,
        format=fmt,
        size=candidate.size,
        completion=1.0,
        nzb="",
        source_subject=candidate.subject_stem,
    )
    return release, tuple(candidate.headers)


def index_batches(
    batches: Iterable[IndexBatch],
    repository: ReleaseRepository,
    *,
    batch_size: int = 512,
    max_pending_groups: int = 4096,
    inspect_candidate: Callable[[ReleaseCandidate], None] | None = None,
) -> IndexingStats:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    grouper = StreamingHeaderGrouper(
        max_pending_groups=max_pending_groups,
        inspect_incomplete=inspect_candidate,
    )
    headers_received = 0
    candidates_completed = 0
    releases_indexed = 0
    releases_rejected = 0
    duplicate_releases = 0
    records: list[tuple[IndexedRelease, tuple[ArticleHeader, ...]]] = []

    def commit_records(checkpoint: IndexCheckpoint | None = None) -> None:
        nonlocal releases_indexed, duplicate_releases
        accepted = len(records)
        inserted = repository.commit_index_batch(records, checkpoint)
        releases_indexed += inserted
        duplicate_releases += accepted - inserted
        records.clear()

    def process_candidate(candidate: ReleaseCandidate) -> None:
        nonlocal candidates_completed, releases_rejected
        candidates_completed += 1
        record = _release_record(candidate, inspect_candidate)
        if record is None:
            releases_rejected += 1
            return
        records.append(record)
        if len(records) >= batch_size:
            commit_records()

    for batch in batches:
        for header in batch.headers:
            headers_received += 1
            candidate = grouper.feed_one(header)
            if candidate is not None:
                process_candidate(candidate)
        commit_records(batch.checkpoint)

    for candidate in grouper.flush():
        process_candidate(candidate)
    if records:
        commit_records()

    return IndexingStats(
        headers_received=headers_received,
        candidates_completed=candidates_completed,
        releases_indexed=releases_indexed,
        releases_rejected=releases_rejected,
        duplicate_releases=duplicate_releases,
    )


def index_headers(headers: list[ArticleHeader], repository: ReleaseRepository) -> list[IndexedRelease]:
    existing_ids = {release.id for release in repository.search("")}
    index_batches(
        [IndexBatch(headers=headers)],
        repository,
        max_pending_groups=max(1, min(len(headers), 4096)),
    )
    return [release for release in repository.search("") if release.id not in existing_ids]
