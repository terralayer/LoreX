import pytest

from lorex.domain import ArticleHeader, IndexCheckpoint, IndexedRelease
from lorex.indexer.grouping import StreamingHeaderGrouper, normalize_header
from lorex.indexer.nzb import get_or_build_nzb
from lorex.repository import ReleaseRepository
from lorex.services.indexing import IndexBatch, index_batches


def _header(part: int, total: int, *, book: str = "Project Hail Mary", message: str | None = None) -> ArticleHeader:
    return ArticleHeader(
        message_id=message or f"<{book.replace(' ', '-').lower()}-{part}@example.test>",
        subject=f"Andy Weir - {book} - Ray Porter.m4b [{part}/{total}]",
        bytes=10_000_000 + part,
    )


def _release(release_id: str, *, title: str = "Project Hail Mary") -> IndexedRelease:
    return IndexedRelease(
        id=release_id,
        title=title,
        author="Andy Weir",
        narrator="Ray Porter",
        format="m4b",
        size=30_000_006,
        completion=1.0,
        nzb="",
        source_subject=f"Andy Weir - {title} - Ray Porter.m4b",
    )


def test_normalize_header_extracts_subject_and_part_metadata():
    normalized = normalize_header(_header(2, 3))

    assert normalized.subject_stem == "Andy Weir - Project Hail Mary - Ray Porter.m4b"
    assert normalized.part_number == 2
    assert normalized.total_parts == 3


def test_streaming_grouper_completes_multipart_across_feeds():
    grouper = StreamingHeaderGrouper(max_pending_groups=8)

    assert grouper.feed(_header(1, 3)) == []
    assert grouper.feed(_header(2, 3)) == []
    completed = grouper.feed(_header(3, 3))

    assert len(completed) == 1
    assert [item.message_id for item in completed[0].headers] == [
        "<project-hail-mary-1@example.test>",
        "<project-hail-mary-2@example.test>",
        "<project-hail-mary-3@example.test>",
    ]
    assert grouper.pending_count == 0


def test_streaming_grouper_deduplicates_repeated_part_numbers():
    grouper = StreamingHeaderGrouper(max_pending_groups=8)

    assert grouper.feed(_header(1, 2, message="<first-copy@example.test>")) == []
    assert grouper.feed(_header(1, 2, message="<duplicate-copy@example.test>")) == []
    completed = grouper.feed(_header(2, 2))

    assert len(completed) == 1
    assert [item.message_id for item in completed[0].headers] == [
        "<first-copy@example.test>",
        "<project-hail-mary-2@example.test>",
    ]


def test_streaming_grouper_bounds_pending_groups_and_routes_eviction_to_inspection():
    inspected = []
    grouper = StreamingHeaderGrouper(max_pending_groups=1, inspect_incomplete=inspected.append)

    assert grouper.feed(_header(1, 2, book="Book One")) == []
    assert grouper.pending_count == 1
    assert grouper.feed(_header(1, 2, book="Book Two")) == []

    assert grouper.pending_count == 1
    assert len(inspected) == 1
    assert inspected[0].subject_stem == "Andy Weir - Book One - Ray Porter.m4b"
    assert len(inspected[0].headers) == 1


def test_commit_index_batch_persists_release_articles_and_checkpoint():
    repository = ReleaseRepository()
    release = _release("release-one")
    articles = tuple(_header(part, 3) for part in range(1, 4))
    checkpoint = IndexCheckpoint("backfill", articles[0].group, 100)

    inserted = repository.commit_index_batch([(release, articles)], checkpoint)

    assert inserted == 1
    assert repository.get(release.id) == release
    assert repository.get_articles(release.id) == articles
    assert repository.get_checkpoint("backfill", articles[0].group) == checkpoint


def test_commit_index_batch_rejects_regressing_checkpoint_without_partial_mutation():
    repository = ReleaseRepository()
    group = "alt.binaries.audiobooks"
    first = _release("release-one")
    second = _release("release-two", title="The Martian")
    first_articles = (_header(1, 1),)
    second_articles = (_header(1, 1, book="The Martian"),)

    assert repository.commit_index_batch(
        [(first, first_articles)],
        IndexCheckpoint("backfill", group, 100),
    ) == 1

    with pytest.raises(ValueError, match="checkpoint"):
        repository.commit_index_batch(
            [(second, second_articles)],
            IndexCheckpoint("backfill", group, 99),
        )

    assert repository.get(second.id) is None
    assert repository.get_articles(second.id) == ()
    assert repository.get_checkpoint("backfill", group) == IndexCheckpoint("backfill", group, 100)


def test_commit_index_batch_deduplicates_live_backfill_overlap():
    repository = ReleaseRepository()
    release = _release("release-one")
    articles = tuple(_header(part, 3) for part in range(1, 4))

    assert repository.commit_index_batch([(release, articles)]) == 1
    assert repository.commit_index_batch([(release, articles)]) == 0

    assert len(repository._items) == 1
    assert repository.get_articles(release.id) == articles


def test_index_batches_streams_across_batches_commits_checkpoint_and_keeps_nzb_lazy():
    repository = ReleaseRepository()
    inspected = []
    group = "alt.binaries.audiobooks"
    headers = tuple(_header(part, 3) for part in range(1, 4))
    checkpoint = IndexCheckpoint("backfill", group, 123456)

    stats = index_batches(
        [
            IndexBatch(headers=headers[:2]),
            IndexBatch(headers=headers[2:], checkpoint=checkpoint),
        ],
        repository,
        max_pending_groups=8,
        inspect_candidate=inspected.append,
    )

    assert stats.headers_received == 3
    assert stats.candidates_completed == 1
    assert stats.releases_indexed == 1
    assert stats.releases_rejected == 0
    assert stats.duplicate_releases == 0
    assert len(inspected) == 1

    release = next(iter(repository._items.values()))
    assert release.title == "Project Hail Mary"
    assert release.author == "Andy Weir"
    assert release.narrator == "Ray Porter"
    assert release.nzb == ""
    assert repository.get_articles(release.id) == headers
    assert repository.get_checkpoint("backfill", group) == checkpoint


def test_index_batches_replay_counts_overlap_as_duplicate():
    repository = ReleaseRepository()
    group = "alt.binaries.audiobooks"
    headers = tuple(_header(part, 3) for part in range(1, 4))
    batches = [
        IndexBatch(headers=headers[:2]),
        IndexBatch(headers=headers[2:], checkpoint=IndexCheckpoint("backfill", group, 100)),
    ]

    first = index_batches(batches, repository, max_pending_groups=8)
    second = index_batches(batches, repository, max_pending_groups=8)

    assert first.releases_indexed == 1
    assert first.duplicate_releases == 0
    assert second.releases_indexed == 0
    assert second.duplicate_releases == 1
    assert len(repository._items) == 1


def test_get_or_build_nzb_builds_once_from_persisted_articles_then_uses_cache():
    repository = ReleaseRepository()
    headers = tuple(_header(part, 3) for part in range(1, 4))
    index_batches([IndexBatch(headers=headers)], repository, max_pending_groups=8)
    release = next(iter(repository._items.values()))

    first = get_or_build_nzb(release.id, repository)

    assert first.startswith("<?xml")
    assert repository.get_cached_nzb(release.id) == first
    for header in headers:
        assert header.message_id.strip("<>") in first

    repository._articles.clear()
    second = get_or_build_nzb(release.id, repository)
    assert second == first
