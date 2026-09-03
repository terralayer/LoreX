from __future__ import annotations

from pathlib import Path

import pytest

from lorex.domain import DownloadResult, ImportJob, LibraryBook
from lorex.library.media import MediaAction, MediaProbe
from lorex.library.pipeline import ImportPipeline


class State:
    def __init__(self) -> None:
        self.stages: list[str] = []
        self.completed = False
        self.failed = False

    def set_stage(self, job_id: str, stage: str) -> None:
        self.stages.append(stage)

    def mark_completed(self, job_id: str, final_path: str) -> None:
        self.completed = True

    def mark_failed(self, job_id: str, error: str) -> None:
        self.failed = True


class Library:
    def __init__(self) -> None:
        self.books: list[LibraryBook] = []

    def add(self, book: LibraryBook) -> LibraryBook:
        self.books.append(book)
        return book


def _result() -> DownloadResult:
    return DownloadResult("r1", "Book", "Author", "Narrator", "m4b", "Book.m4b", 5)


def test_valid_m4b_preserve_path_reaches_library_without_transcode(tmp_path: Path) -> None:
    source = tmp_path / "source.m4b"
    source.write_bytes(b"audio")
    state = State()
    library = Library()
    calls: list[str] = []
    pipeline = ImportPipeline(
        state=state,
        library=library,
        library_root=tmp_path / "library",
        verify=lambda path: True,
        probe=lambda path: MediaProbe("mov,mp4,m4a", "aac", True),
        remux=lambda src, dst: calls.append("remux"),
        transcode=lambda src, dst: calls.append("transcode"),
        tag=lambda path, result: calls.append("tag"),
    )

    book = pipeline.process(ImportJob("i1", "r1", str(source)), _result())

    assert book.path.endswith("/Author/Book/Book.m4b")
    assert state.completed is True
    assert calls == ["tag"]
    assert "final_verification" in state.stages
    assert source.exists() is False


def test_final_verification_failure_never_cleans_source(tmp_path: Path) -> None:
    source = tmp_path / "source.m4b"
    source.write_bytes(b"audio")
    state = State()
    pipeline = ImportPipeline(
        state=state,
        library=Library(),
        library_root=tmp_path / "library",
        verify=lambda path: path == source,
        probe=lambda path: MediaProbe("mov,mp4,m4a", "aac", True),
        remux=lambda src, dst: None,
        transcode=lambda src, dst: None,
        tag=lambda path, result: None,
    )

    with pytest.raises(ValueError):
        pipeline.process(ImportJob("i1", "r1", str(source)), _result())

    assert source.exists()
    assert state.failed is True
