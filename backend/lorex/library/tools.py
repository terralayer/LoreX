from __future__ import annotations

from dataclasses import dataclass
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

    def run(self, command: Sequence[str], gate: BoundedSemaphore) -> CompletedProcess[str]:
        if not command:
            raise ValueError("command must not be empty")
        with gate:
            return run(list(command), check=True, capture_output=True, text=True, shell=False)
