from __future__ import annotations

import pytest

from lorex.library.archive import ArchiveLimits, ArchiveMember, ArchiveSafetyError, validate_archive_members


def test_safe_nested_archive_is_accepted() -> None:
    manifest = validate_archive_members(
        [ArchiveMember("Book/Disc 1/chapter01.m4b", 1024)],
        ArchiveLimits(max_files=10, max_extracted_bytes=4096),
    )
    assert manifest.file_count == 1
    assert manifest.extracted_bytes == 1024


@pytest.mark.parametrize("name", ["../escape.m4b", "/absolute.m4b", "Book/../../escape.m4b"])
def test_archive_traversal_is_rejected(name: str) -> None:
    with pytest.raises(ArchiveSafetyError):
        validate_archive_members([ArchiveMember(name, 1)], ArchiveLimits(10, 4096))


def test_archive_file_count_and_size_are_bounded() -> None:
    with pytest.raises(ArchiveSafetyError):
        validate_archive_members([ArchiveMember("a", 1), ArchiveMember("b", 1)], ArchiveLimits(1, 4096))
    with pytest.raises(ArchiveSafetyError):
        validate_archive_members([ArchiveMember("a", 4097)], ArchiveLimits(10, 4096))
