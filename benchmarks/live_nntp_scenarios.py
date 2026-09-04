from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Lock
from time import perf_counter, sleep
import tracemalloc

from lorex.downloader.provider import ProviderConfig, ProviderPool
from lorex.nntp.client import NntpClient

FAKE_USERNAME = "lorex-benchmark-user"
FAKE_PASSWORD = "lorex-benchmark-password"
_MIB = 1024 * 1024


def _peak_python_mb(fn):
    tracemalloc.start()
    try:
        started = perf_counter()
        result = fn()
        elapsed = perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, elapsed, peak / _MIB


def benchmark_overview_parse(rows: int = 10_000) -> dict[str, int | float]:
    if rows < 1:
        raise ValueError("rows must be positive")
    payload = b"".join(
        (
            f"{number}\tAuthor {number} - Book {number}.m4b [1/1]\tposter\tdate\t<{number}@bench.test>\t\t1048576\t10\r\n".encode()
            for number in range(1, rows + 1)
        )
    ) + b".\r\n"

    def parse() -> int:
        client = NntpClient("benchmark.invalid")
        client._reader = BytesIO(payload)
        return sum(1 for _ in client._read_overview_rows())

    parsed, elapsed, peak_mb = _peak_python_mb(parse)
    return {
        "rows": parsed,
        "elapsed_ms": elapsed * 1000.0,
        "rows_per_second": parsed / elapsed if elapsed else 0.0,
        "peak_python_mb": peak_mb,
    }


class _BodyFixtureProvider:
    def __init__(self, total_bytes: int, chunk_size: int = 65_536) -> None:
        self.total_bytes = total_bytes
        self.chunk = b"x" * chunk_size

    def stream_article(self, message_id: str):
        remaining = self.total_bytes
        while remaining:
            chunk = self.chunk if remaining >= len(self.chunk) else self.chunk[:remaining]
            remaining -= len(chunk)
            yield chunk


def benchmark_body_stream(total_bytes: int = 64 * _MIB) -> dict[str, int | float]:
    if total_bytes < 1:
        raise ValueError("total_bytes must be positive")
    config = ProviderConfig(name="BodyFixture", host="benchmark.invalid", max_connections=1)
    pool = ProviderPool(config, _BodyFixtureProvider(total_bytes))

    def consume() -> int:
        return sum(len(chunk) for chunk in pool.stream_article("<body@bench.test>"))

    streamed, elapsed, peak_mb = _peak_python_mb(consume)
    return {
        "bytes": streamed,
        "elapsed_ms": elapsed * 1000.0,
        "throughput_mib_s": (streamed / _MIB) / elapsed if elapsed else 0.0,
        "peak_python_mb": peak_mb,
    }


class _ConcurrencyFixtureProvider:
    def __init__(self) -> None:
        self._lock = Lock()
        self.active = 0
        self.observed_max = 0
        self.chunk = b"fixture"

    def stream_article(self, message_id: str):
        with self._lock:
            self.active += 1
            self.observed_max = max(self.observed_max, self.active)
        try:
            sleep(0.01)
            yield self.chunk
        finally:
            with self._lock:
                self.active -= 1


def benchmark_provider_concurrency(configured_max: int = 4, requests: int = 24) -> dict[str, int]:
    if configured_max < 1 or requests < 1:
        raise ValueError("configured_max and requests must be positive")
    fixture = _ConcurrencyFixtureProvider()
    config = ProviderConfig(
        name="ConcurrencyFixture",
        host="benchmark.invalid",
        max_connections=configured_max,
    )
    pool = ProviderPool(config, fixture)

    def consume(number: int) -> int:
        return sum(len(chunk) for chunk in pool.stream_article(f"<{number}@bench.test>"))

    with ThreadPoolExecutor(max_workers=max(configured_max * 3, 8)) as executor:
        list(executor.map(consume, range(requests)))

    return {
        "configured_max": configured_max,
        "observed_max": fixture.observed_max,
        "requests": requests,
    }


def run_live_nntp_benchmarks() -> dict:
    return {
        "overview": benchmark_overview_parse(),
        "body": benchmark_body_stream(),
        "provider_concurrency": benchmark_provider_concurrency(),
        "provider": {
            "host": "benchmark.invalid",
            "username_configured": True,
            "password_configured": True,
        },
    }
