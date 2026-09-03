from __future__ import annotations

from pathlib import Path
from hashlib import sha1
from typing import Any, Callable

from lorex.domain import DownloadResult, ImportJob, LibraryBook
from lorex.library.filesystem import promote_verified_file
from lorex.library.importer import sanitize_component
from lorex.library.media import MediaAction, MediaProbe, choose_media_action


class ImportPipeline:
    def __init__(
        self,
        *,
        state: Any,
        library: Any,
        library_root: Path,
        verify: Callable[[Path], bool],
        probe: Callable[[Path], MediaProbe],
        remux: Callable[[Path, Path], None],
        transcode: Callable[[Path, Path], None],
        tag: Callable[[Path, DownloadResult], None],
    ) -> None:
        self.state = state
        self.library = library
        self.library_root = Path(library_root)
        self.verify = verify
        self.probe = probe
        self.remux = remux
        self.transcode = transcode
        self.tag = tag

    def process(self, job: ImportJob, result: DownloadResult) -> LibraryBook:
        source = Path(job.source_path)
        try:
            self.state.set_stage(job.id, "verifying")
            if not self.verify(source):
                raise ValueError("source verification failed")

            self.state.set_stage(job.id, "probing")
            media_probe = self.probe(source)
            action = choose_media_action(media_probe)
            candidate = source

            if action is MediaAction.REMUX:
                self.state.set_stage(job.id, "processing")
                candidate = source.with_suffix(".remux.m4b")
                self.remux(source, candidate)
            elif action is MediaAction.TRANSCODE:
                self.state.set_stage(job.id, "processing")
                candidate = source.with_suffix(".transcoded.m4b")
                self.transcode(source, candidate)

            self.state.set_stage(job.id, "tagging")
            self.tag(candidate, result)

            self.state.set_stage(job.id, "final_verification")
            if not self.verify(candidate):
                raise ValueError("final media verification failed")

            author = sanitize_component(result.author)
            title = sanitize_component(result.title)
            destination = self.library_root / author / title / f"{title}.m4b"

            self.state.set_stage(job.id, "moving")
            size = promote_verified_file(candidate, destination, self.verify)

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
            stored = self.library.add(book)

            if candidate != source:
                source.unlink(missing_ok=True)
            self.state.mark_completed(job.id, final_path=str(destination))
            return stored
        except Exception as exc:
            self.state.mark_failed(job.id, error=str(exc))
            raise
