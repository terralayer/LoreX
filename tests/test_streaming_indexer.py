import lorex.domain as domain
from lorex.domain import ArticleHeader
from lorex.indexer.grouping import StreamingHeaderGrouper, normalize_header
from lorex.repository import ReleaseRepository


def _header(part: int, total: int, *, book: str = "Project Hail Mary", message: str | None = None) -> ArticleHeader:
    return ArticleHeader(
        message_id=message or f"<{book.replace(' ', '-').lower()}-{part}@example.test>",
        subject=f"Andy Weir - {book} - Ray Porter.m4b [{part}/{total}]",
        bytes=10_000_000 + part,
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


def test_index_batch_persistence_api_exists():
    repository = ReleaseRepository()

    assert hasattr(domain, "IndexCheckpoint")
    assert hasattr(repository, "commit_index_batch")
    assert hasattr(repository, "get_checkpoint")
    assert hasattr(repository, "get_articles")
    assert hasattr(repository, "get_cached_nzb")
    assert hasattr(repository, "cache_nzb")
