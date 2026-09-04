from __future__ import annotations

from pathlib import Path

import pytest

from lorex.domain import DownloadResult
from lorex.library.importer import LibraryImporter
from lorex.repository import LibraryRepository


def result(source: Path) -> DownloadResult:
    return DownloadResult(
        release_id="release-1",
        title="Synthetic Book",
        author="Synthetic Author",
        narrator="Synthetic Narrator",
        format="m4b",
        file_name=source.name,
        size=source.stat().st_size if source.exists() else 0,
    )


def test_import_file_moves_real_audio_before_persisting_book(tmp_path: Path) -> None:
    source = tmp_path / "staging" / "Synthetic Book.m4b"
    source.parent.mkdir()
    source.write_bytes(b"synthetic-audio")
    repository = LibraryRepository()
    importer = LibraryImporter(repository, root=str(tmp_path / "library"))

    book = importer.import_file(result(source), source)

    destination = Path(book.path)
    assert destination.is_file()
    assert destination.read_bytes() == b"synthetic-audio"
    assert not source.exists()
    assert repository.get(book.id) == book
    assert book.size == len(b"synthetic-audio")


def test_import_file_refuses_missing_source_without_creating_db_row(tmp_path: Path) -> None:
    source = tmp_path / "missing.m4b"
    repository = LibraryRepository()
    importer = LibraryImporter(repository, root=str(tmp_path / "library"))

    with pytest.raises(FileNotFoundError):
        importer.import_file(
            DownloadResult(
                release_id="release-1",
                title="Synthetic Book",
                author="Synthetic Author",
                narrator=None,
                format="m4b",
                file_name="missing.m4b",
                size=0,
            ),
            source,
        )

    assert repository.search("") == []
