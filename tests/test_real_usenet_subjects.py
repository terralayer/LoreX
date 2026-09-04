from lorex.domain import ArticleHeader
from lorex.indexer.grouping import normalize_header
from lorex.repository import ReleaseRepository
from lorex.services.indexing import IndexBatch, index_batches


def _header(message_id: str, subject: str) -> ArticleHeader:
    return ArticleHeader(
        message_id=message_id,
        subject=subject,
        bytes=1024,
        group="alt.binaries.audiobooks",
    )


def test_normalize_real_yenc_subject_extracts_quoted_filename_and_chunk():
    header = _header(
        "<one@example.test>",
        'Fantasy - [01/26] - "Adam Wright - Harbinger PI.m4b" yEnc (01/123)',
    )

    normalized = normalize_header(header)

    assert normalized.subject_stem == "Adam Wright - Harbinger PI.m4b"
    assert normalized.part_number == 1
    assert normalized.total_parts == 123


def test_real_yenc_direct_audio_indexes_from_audiobook_group():
    repository = ReleaseRepository()
    headers = [
        _header(
            f"<audio-{part}@example.test>",
            f'Fantasy - [01/26] - "Adam Wright - Harbinger PI.m4b" yEnc ({part}/2)',
        )
        for part in (1, 2)
    ]

    stats = index_batches([IndexBatch(headers=headers)], repository)

    assert stats.headers_received == 2
    assert stats.releases_indexed == 1
    release = repository.search("")[0]
    assert release.author == "Adam Wright"
    assert release.title == "Harbinger PI"
    assert release.format == "m4b"
    assert repository.get_articles(release.id) == tuple(headers)


def test_real_yenc_archive_parts_group_into_one_downloadable_release():
    repository = ReleaseRepository()
    headers = [
        _header(
            "<par2@example.test>",
            'monkeewrench - [142/154] - "P.J. Tracy - The Sixth Idea.par2" yEnc (1/1)',
        ),
        _header(
            "<rar-1@example.test>",
            'monkeewrench - [143/154] - "P.J. Tracy - The Sixth Idea.part1.rar" yEnc (1/1)',
        ),
        _header(
            "<rar-2@example.test>",
            'monkeewrench - [144/154] - "P.J. Tracy - The Sixth Idea.part2.rar" yEnc (1/1)',
        ),
    ]

    stats = index_batches([IndexBatch(headers=headers)], repository)

    assert stats.releases_indexed == 1
    release = repository.search("")[0]
    assert release.author == "P.J. Tracy"
    assert release.title == "The Sixth Idea"
    assert release.format == "archive"
    assert repository.get_articles(release.id) == tuple(headers)


def test_software_archive_in_audiobook_group_is_rejected():
    repository = ReleaseRepository()
    headers = [
        _header(
            "<maya-par2@example.test>",
            'poster - [1/3] - "Autodesk Maya v2027.2 (x64) + Fix.par2" yEnc (1/1)',
        ),
        _header(
            "<maya-rar@example.test>",
            'poster - [2/3] - "Autodesk Maya v2027.2 (x64) + Fix.part1.rar" yEnc (1/1)',
        ),
    ]

    stats = index_batches([IndexBatch(headers=headers)], repository)

    assert stats.headers_received == 2
    assert stats.releases_indexed == 0
    assert stats.releases_rejected == 1
    assert repository.search("") == []
