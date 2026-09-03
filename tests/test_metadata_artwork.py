from __future__ import annotations

import threading
import time

from lorex.metadata.artwork import ArtworkScheduler
from lorex.metadata.cache import InMemoryMetadataCache
from lorex.metadata.metrics import MetadataMetrics
from lorex.metadata.model import BookMetadata, MetadataLookup, ProviderOutcome
from lorex.metadata.resolver import MetadataResolver


class ArtworkProvider:
    name = "fake"

    def lookup(self, lookup: MetadataLookup) -> ProviderOutcome:
        return ProviderOutcome.found(
            BookMetadata(
                title="Project Hail Mary",
                authors=("Andy Weir",),
                source=self.name,
                artwork_url="https://example.test/cover.jpg",
            )
        )


def test_submit_is_nonblocking_and_duplicate_keys_coalesce():
    started = threading.Event()
    release = threading.Event()

    def worker(key: str, url: str) -> None:
        started.set()
        release.wait(2)

    metrics = MetadataMetrics()
    scheduler = ArtworkScheduler(worker, max_workers=1, queue_size=1, metrics=metrics)
    try:
        assert scheduler.submit("same-key", "https://example.test/a.jpg") is True
        assert started.wait(1)
        assert scheduler.submit("same-key", "https://example.test/a.jpg") is False
        snapshot = metrics.snapshot()
        assert snapshot["artwork_scheduled"] == 1
        assert snapshot["artwork_deduplicated"] == 1
    finally:
        release.set()
        scheduler.close()


def test_worker_concurrency_never_exceeds_configured_limit():
    active = 0
    max_active = 0
    lock = threading.Lock()

    def worker(key: str, url: str) -> None:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with lock:
            active -= 1

    scheduler = ArtworkScheduler(worker, max_workers=2, queue_size=10)
    try:
        for index in range(8):
            assert scheduler.submit(f"key-{index}", f"https://example.test/{index}.jpg") is True
    finally:
        scheduler.close()

    assert scheduler.max_workers == 2
    assert max_active == 2


def test_queue_is_bounded_and_full_queue_drops_without_blocking():
    started = threading.Event()
    release = threading.Event()
    metrics = MetadataMetrics()

    def worker(key: str, url: str) -> None:
        started.set()
        release.wait(2)

    scheduler = ArtworkScheduler(worker, max_workers=1, queue_size=0, metrics=metrics)
    try:
        assert scheduler.submit("first", "https://example.test/1.jpg") is True
        assert started.wait(1)
        assert scheduler.submit("second", "https://example.test/2.jpg") is False
        assert metrics.snapshot()["artwork_dropped"] == 1
    finally:
        release.set()
        scheduler.close()


def test_artwork_failure_does_not_fail_bibliographic_resolution():
    def worker(key: str, url: str) -> None:
        raise RuntimeError("image failed")

    scheduler = ArtworkScheduler(worker, max_workers=1, queue_size=1)
    resolver = MetadataResolver(
        cache=InMemoryMetadataCache(),
        providers=(ArtworkProvider(),),
        artwork_scheduler=scheduler,
    )
    try:
        result = resolver.resolve(MetadataLookup(isbn13="9780063279327"))
        assert result is not None
        assert result.title == "Project Hail Mary"
    finally:
        scheduler.close()
