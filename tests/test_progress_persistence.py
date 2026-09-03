from __future__ import annotations

from lorex.downloader.progress import ProgressCoalescer


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class CountingSink:
    def __init__(self) -> None:
        self.write_count = 0
        self.total = 0

    def persist_progress(self, byte_count: int) -> None:
        self.write_count += 1
        self.total += byte_count


def test_terminal_flush_persists_pending_progress_once() -> None:
    clock = Clock()
    sink = CountingSink()
    coalescer = ProgressCoalescer(1024, 5.0, clock=clock)
    for _ in range(10):
        coalescer.record(50)
        coalescer.flush_if_needed(sink)

    coalescer.flush(sink)

    assert sink.write_count == 1
    assert sink.total == 500
