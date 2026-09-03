from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import Protocol


class ProgressSink(Protocol):
    def persist_progress(self, byte_count: int) -> None: ...


class ProgressCoalescer:
    def __init__(
        self,
        byte_threshold: int,
        time_threshold_seconds: float,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if byte_threshold <= 0:
            raise ValueError("byte_threshold must be positive")
        if time_threshold_seconds <= 0:
            raise ValueError("time_threshold_seconds must be positive")
        self.byte_threshold = byte_threshold
        self.time_threshold_seconds = time_threshold_seconds
        self._clock = clock
        self._pending_bytes = 0
        self._last_flush = clock()

    @property
    def pending_bytes(self) -> int:
        return self._pending_bytes

    def record(self, byte_count: int) -> None:
        if byte_count < 0:
            raise ValueError("byte_count cannot be negative")
        self._pending_bytes += byte_count

    def should_flush(self) -> bool:
        if self._pending_bytes <= 0:
            return False
        return (
            self._pending_bytes >= self.byte_threshold
            or self._clock() - self._last_flush >= self.time_threshold_seconds
        )

    def flush_if_needed(self, sink: ProgressSink) -> bool:
        if not self.should_flush():
            return False
        self.flush(sink)
        return True

    def flush(self, sink: ProgressSink) -> int:
        if self._pending_bytes <= 0:
            return 0
        amount = self._pending_bytes
        sink.persist_progress(amount)
        self._pending_bytes = 0
        self._last_flush = self._clock()
        return amount
