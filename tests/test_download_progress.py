from __future__ import annotations

from dataclasses import dataclass

from lorex.downloader.progress import ProgressCoalescer


@dataclass
class FakeClock:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value


class Sink:
    def __init__(self) -> None:
        self.writes: list[int] = []

    def persist_progress(self, byte_count: int) -> None:
        self.writes.append(byte_count)


def test_progress_coalesces_subthreshold_updates() -> None:
    clock = FakeClock()
    sink = Sink()
    coalescer = ProgressCoalescer(byte_threshold=1024, time_threshold_seconds=5.0, clock=clock)

    for _ in range(7):
        coalescer.record(100)
        coalescer.flush_if_needed(sink)

    assert sink.writes == []

    coalescer.record(400)
    coalescer.flush_if_needed(sink)
    assert sink.writes == [1100]


def test_progress_time_threshold_and_terminal_flush() -> None:
    clock = FakeClock()
    sink = Sink()
    coalescer = ProgressCoalescer(byte_threshold=10_000, time_threshold_seconds=5.0, clock=clock)

    coalescer.record(250)
    clock.value = 5.1
    coalescer.flush_if_needed(sink)
    assert sink.writes == [250]

    coalescer.record(50)
    coalescer.flush(sink)
    assert sink.writes == [250, 50]
