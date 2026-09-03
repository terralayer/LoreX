from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess, run
from threading import BoundedSemaphore
from typing import Sequence


@dataclass(frozen=True, slots=True)
class MediaWorkerLimits:
    repair: int = 1
    extraction: int = 1
    ffmpeg: int = 1

    def __post_init__(self) -> None:
        if self.repair <= 0 or self.extraction <= 0 or self.ffmpeg <= 0:
            raise ValueError("media worker limits must be positive")


class ToolRunner:
    def __init__(self, limits: MediaWorkerLimits) -> None:
        self.repair_gate = BoundedSemaphore(limits.repair)
        self.extraction_gate = BoundedSemaphore(limits.extraction)
        self.ffmpeg_gate = BoundedSemaphore(limits.ffmpeg)

    def _execute(self, command: Sequence[str], gate: BoundedSemaphore) -> CompletedProcess[str]:
        if not command:
            raise ValueError("command must not be empty")
        with gate:
            return run(list(command), check=True, capture_output=True, text=True, shell=False)

    def run(self, command: Sequence[str], gate: BoundedSemaphore) -> CompletedProcess[str]:
        return self._execute(command, gate)

    def par2_verify(self, par2_file: Path) -> CompletedProcess[str]:
        return self._execute(["par2", "verify", str(par2_file)], self.repair_gate)

    def par2_repair(self, par2_file: Path) -> CompletedProcess[str]:
        return self._execute(["par2", "repair", str(par2_file)], self.repair_gate)

    def extract_7z(self, archive: Path, target: Path) -> CompletedProcess[str]:
        target.mkdir(parents=True, exist_ok=True)
        return self._execute(["7z", "x", "-y", f"-o{target}", str(archive)], self.extraction_gate)

    def ffprobe(self, source: Path) -> CompletedProcess[str]:
        return self._execute(
            [
                "ffprobe",
                "-v",
                "error",
                "-of",
                "json",
                "-show_format",
                "-show_streams",
                str(source),
            ],
            self.ffmpeg_gate,
        )

    def ffmpeg_remux(self, source: Path, target: Path) -> CompletedProcess[str]:
        return self._execute(
            ["ffmpeg", "-y", "-i", str(source), "-map", "0", "-c", "copy", str(target)],
            self.ffmpeg_gate,
        )

    def ffmpeg_transcode(self, source: Path, target: Path) -> CompletedProcess[str]:
        return self._execute(
            ["ffmpeg", "-y", "-i", str(source), "-map", "0:a", "-c:a", "aac", str(target)],
            self.ffmpeg_gate,
        )
