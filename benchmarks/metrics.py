from __future__ import annotations

import math
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - Windows fallback
    resource = None


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    name: str
    sample_count: int
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    mean_ms: float
    peak_python_mb: float
    peak_rss_mb: float

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= q <= 1.0:
        raise ValueError("percentile q must be between 0 and 1")

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]

    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _peak_rss_mb() -> float:
    if resource is None:
        return 0.0
    peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return peak / (1024 * 1024)
    return peak / 1024


def measure_samples(
    name: str,
    fn: Callable[[], Any],
    samples: int,
    warmups: int = 1,
) -> BenchmarkResult:
    if samples < 1:
        raise ValueError("samples must be at least 1")
    if warmups < 0:
        raise ValueError("warmups cannot be negative")

    for _ in range(warmups):
        fn()

    elapsed_ms: list[float] = []
    tracemalloc.start()
    try:
        for _ in range(samples):
            started = time.perf_counter()
            fn()
            elapsed_ms.append((time.perf_counter() - started) * 1000)
        _, peak_python_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    return BenchmarkResult(
        name=name,
        sample_count=samples,
        p50_ms=percentile(elapsed_ms, 0.50),
        p95_ms=percentile(elapsed_ms, 0.95),
        min_ms=min(elapsed_ms),
        max_ms=max(elapsed_ms),
        mean_ms=statistics.fmean(elapsed_ms),
        peak_python_mb=peak_python_bytes / (1024 * 1024),
        peak_rss_mb=_peak_rss_mb(),
    )
