from __future__ import annotations

import os
from hashlib import sha1
from pathlib import Path
from typing import Any, Callable

from lorex.domain import DownloadResult, ImportJob, LibraryBook
from lorex.library.filesystem import promote_verified_file
from lorex.library.importer import sanitize_component
from lorex.library.media import MediaAction, MediaProbe, choose_media_action

_STAGE_ORDER = {
    "verify": 0,
    "verifying": 0,
    "repairing": 1,
    "extracting": 2,
    "probing": 3,
    "processing": 4,
    "tagging": 5,
    "final_verification": 6,
    "moving": 7,
    "completed": 8,
}


class ImportPipeline:
    def __init__(
        self,
        *,
        state: Any,
        library: Any,
        library_root: Path,
        verify: Callable[[Path], bool],
        needs_repair: Callable[[Path], bool],
        repair: Callable[[Path], Path],
        needs_extract: Callable[[Path], bool],
        extract: Callable[[Path], Path],
        probe: Callable[[Path], MediaProbe],
        remux: Callable[[Path, Path], None],
        transcode: Callable[[Path, Path], None],
        tag: Callable[[Path, DownloadResult], None],
        cleanup: Callable[[Path, Path | None, Path], None],
    ) -> None:
        self.state = state
        self.library = library
        self.library_root = Path(library_root)
        self.verify = verify
        self.needs_repair = needs_repair
        self.repair = repair
        self.needs_extract = needs_extract
        self.extract = extract
        self.probe = probe
        self.remux = remux
        self.transcode = transcode
        self.tag = tag
        self.cleanup = cleanup

    def _set_staging_path(self, job_id: str, path: Path) -> None:
        setter = getattr(self.state, "set_staging_path", None)
        if setter is not None:
            setter(job_id, str(path))

    def process(self, job: ImportJob, result: DownloadResult) -> LibraryBook:
        source = Path(job.source_path)
        working = Path(job.staging_path) if job.staging_path else source
        stage_rank = _STAGE_ORDER.get(job.stage)
        if stage_rank is None:
            raise ValueError(f"unknown import stage: {job.stage}")
        if stage_rank >= _STAGE_ORDER["completed"]:
            raise ValueError("completed import job cannot be processed again")
        destination: Path | None = None
        promoted_from: Path | None = None

        try:
            if stage_rank <= 0:
                self.state.set_stage(job.id, "verifying")
                if not self.verify(source):
                    raise ValueError("source verification failed")
                self.state.set_stage(job.id, "repairing")

            if stage_rank <= 1:
                if self.needs_repair(working):
                    working = Path(self.repair(working))
                    self._set_staging_path(job.id, working)
                self.state.set_stage(job.id, "extracting")

            if stage_rank <= 2:
                if self.needs_extract(working):
                    working = Path(self.extract(working))
                    self._set_staging_path(job.id, working)
                self.state.set_stage(job.id, "probing")

            if stage_rank <= 4:
                media_probe = self.probe(working)
                action = choose_media_action(media_probe)
                if action is MediaAction.REMUX:
                    candidate = source.with_suffix(".remux.m4b")
                    if not (stage_rank == 4 and candidate.exists()):
                        self.remux(working, candidate)
                    working = candidate
                    self._set_staging_path(job.id, working)
                elif action is MediaAction.TRANSCODE:
                    candidate = source.with_suffix(".transcoded.m4b")
                    if not (stage_rank == 4 and candidate.exists()):
                        self.transcode(working, candidate)
                    working = candidate
                    self._set_staging_path(job.id, working)
                self.state.set_stage(job.id, "tagging")

            if stage_rank <= 5:
                self.tag(working, result)
                self.state.set_stage(job.id, "final_verification")

            if stage_rank <= 6:
                if not self.verify(working):
                    raise ValueError("final media verification failed")
                self.state.set_stage(job.id, "moving")

            author = sanitize_component(result.author)
            title = sanitize_component(result.title)
            destination = self.library_root / author / title / f"{title}.m4b"
            if stage_rank >= 7 and destination.exists() and self.verify(destination):
                size = destination.stat().st_size
                promoted_from = None
            else:
                promoted_from = working
                size = promote_verified_file(working, destination, self.verify)

            book_id = sha1(
                f"{result.author}|{result.title}|{result.narrator or ''}".encode("utf-8")
            ).hexdigest()[:16]
            book = LibraryBook(
                id=book_id,
                title=result.title,
                author=result.author,
                narrator=result.narrator,
                format="m4b",
                path=str(destination),
                size=size,
            )
            try:
                stored = self.library.add(book)
            except Exception:
                if destination.exists() and promoted_from is not None:
                    promoted_from.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(destination, promoted_from)
                raise

            self.state.mark_completed(job.id, final_path=str(destination))
            self.cleanup(source, Path(job.staging_path) if job.staging_path else None, destination)
            return stored
        except Exception as exc:
            self.state.mark_failed(job.id, error=str(exc))
            raise
