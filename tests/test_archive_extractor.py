from __future__ import annotations

from pathlib import Path

import pytest

from lorex.library.archive import ArchiveExtractor, ArchiveLimits, ArchiveMember, ArchiveSafetyError


class Runner:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path]] = []

    def extract_7z(self, archive: Path, target: Path) -> None:
        self.calls.append((archive, target))


def test_extractor_validates_members_before_invoking_7z(tmp_path: Path) -> None:
    runner = Runner()
    archive = tmp_path / "book.7z"
    target = tmp_path / "out"
    extractor = ArchiveExtractor(
        runner,
        lambda path: [ArchiveMember("Book/chapter.m4b", 1024)],
        ArchiveLimits(10, 4096),
    )

    extractor.extract(archive, target)

    assert runner.calls == [(archive, target)]


def test_unsafe_archive_never_reaches_extractor_tool(tmp_path: Path) -> None:
    runner = Runner()
    extractor = ArchiveExtractor(
        runner,
        lambda path: [ArchiveMember("../escape.m4b", 1024)],
        ArchiveLimits(10, 4096),
    )

    with pytest.raises(ArchiveSafetyError):
        extractor.extract(tmp_path / "bad.7z", tmp_path / "out")

    assert runner.calls == []
