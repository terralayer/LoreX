from __future__ import annotations

from pathlib import Path

import pytest

from lorex.domain import DownloadResult, ImportJob, LibraryBook
from lorex.library.media import MediaProbe
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
    def __init__(self, fail: bool = False) -> None:
        self.books: list[LibraryBook] = []
        self.fail = fail

    def add(self, book: LibraryBook) -> LibraryBook:
        if self.fail:
            raise RuntimeError("library persistence failed")
        self.books.append(book)
        return book


def _result() -> DownloadResult:
    return DownloadResult("r1", "Book", "Author", "Narrator", "m4b", "Book.m4b", 5)


def _pipeline(tmp_path: Path, state: State, library: Library, calls: list[str], **overrides) -> ImportPipeline:
    kwargs = dict(
        state=state,
        library=library,
        library_root=tmp_path / "library",
        verify=lambda path: True,
        needs_repair=lambda path: False,
        repair=lambda path: calls.append("repair") or path,
        needs_extract=lambda path: False,
        extract=lambda path: calls.append("extract") or path,
        probe=lambda path: MediaProbe("mov,mp4,m4a", "aac", True),
        remux=lambda src, dst: calls.append("remux"),
        transcode=lambda src, dst: calls.append("transcode"),
        tag=lambda path, result: calls.append("tag"),
    )
    kwargs.update(overrides)
    return ImportPipeline(**kwargs)


def test_valid_m4b_preserve_path_reaches_library_without_transcode(tmp_path: Path) -> None:
    source = tmp_path / "source.m4b"
    source.write_bytes(b"audio")
    state = State()
    calls: list[str] = []

    book = _pipeline(tmp_path, state, Library(), calls).process(ImportJob("i1", "r1", str(source)), _result())

    assert book.path.endswith("/Author/Book/Book.m4b")
    assert state.completed is True
    assert calls == ["tag"]
    assert "final_verification" in state.stages
    assert source.exists() is False


def test_repair_and_extract_stages_run_before_probe(tmp_path: Path) -> None:
    source = tmp_path / "download.par2"
    source.write_bytes(b"parts")
    extracted = tmp_path / "extracted.m4b"
    extracted.write_bytes(b"audio")
    calls: list[str] = []
    pipeline = _pipeline(
        tmp_path,
        State(),
        Library(),
        calls,
        needs_repair=lambda path: True,
        repair=lambda path: calls.append("repair") or path,
        needs_extract=lambda path: True,
        extract=lambda path: calls.append("extract") or extracted,
        probe=lambda path: calls.append("probe") or MediaProbe("mov,mp4,m4a", "aac", True),
    )

    pipeline.process(ImportJob("i1", "r1", str(source)), _result())

    assert calls[:3] == ["repair", "extract", "probe"]


def test_final_verification_failure_never_cleans_source(tmp_path: Path) -> None:
    source = tmp_path / "source.m4b"
    source.write_bytes(b"audio")
    state = State()
    pipeline = _pipeline(tmp_path, state, Library(), [], verify=lambda path: path == source)

    with pytest.raises(ValueError):
        pipeline.process(ImportJob("i1", "r1", str(source)), _result())

    assert source.exists()
    assert state.failed is True


def test_library_persistence_failure_restores_preserved_source(tmp_path: Path) -> None:
    source = tmp_path / "source.m4b"
    source.write_bytes(b"audio")
    destination = tmp_path / "library" / "Author" / "Book" / "Book.m4b"

    with pytest.raises(RuntimeError, match="library persistence failed"):
        _pipeline(tmp_path, State(), Library(fail=True), []).process(ImportJob("i1", "r1", str(source)), _result())

    assert source.read_bytes() == b"audio"
    assert not destination.exists()


def test_resume_from_tagging_reuses_staged_media_without_reprocessing(tmp_path: Path) -> None:
    source = tmp_path / "source.mka"
    source.write_bytes(b"original")
    staged = tmp_path / "source.remux.m4b"
    staged.write_bytes(b"ready")
    calls: list[str] = []
    job = ImportJob("i1", "r1", str(source), stage="tagging", staging_path=str(staged))

    _pipeline(
        tmp_path,
        State(),
        Library(),
        calls,
        probe=lambda path: MediaProbe("matroska", "aac", True),
    ).process(job, _result())

    assert "remux" not in calls
    assert calls == ["tag"]
