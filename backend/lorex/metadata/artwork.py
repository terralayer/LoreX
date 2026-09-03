from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from lorex.metadata.metrics import MetadataMetrics


class ArtworkScheduler:
    def __init__(
        self,
        worker: Callable[[str, str], None],
        *,
        max_workers: int = 2,
        queue_size: int = 32,
        metrics: MetadataMetrics | None = None,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        if queue_size < 0:
            raise ValueError("queue_size cannot be negative")
        self.worker = worker
        self.max_workers = max_workers
        self.queue_size = queue_size
        self.metrics = metrics or MetadataMetrics()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="lorex-artwork")
        self._capacity = threading.BoundedSemaphore(max_workers + queue_size)
        self._active: set[str] = set()
        self._lock = threading.Lock()
        self._closed = False

    def submit(self, cache_key: str, url: str) -> bool:
        with self._lock:
            if self._closed:
                self.metrics.increment("artwork_dropped")
                return False
            if cache_key in self._active:
                self.metrics.increment("artwork_deduplicated")
                return False

        if not self._capacity.acquire(blocking=False):
            self.metrics.increment("artwork_dropped")
            return False

        with self._lock:
            if self._closed:
                self._capacity.release()
                self.metrics.increment("artwork_dropped")
                return False
            if cache_key in self._active:
                self._capacity.release()
                self.metrics.increment("artwork_deduplicated")
                return False
            self._active.add(cache_key)

        try:
            self._executor.submit(self._run, cache_key, url)
        except RuntimeError:
            with self._lock:
                self._active.discard(cache_key)
            self._capacity.release()
            self.metrics.increment("artwork_dropped")
            return False

        self.metrics.increment("artwork_scheduled")
        return True

    def _run(self, cache_key: str, url: str) -> None:
        try:
            self.worker(cache_key, url)
        except Exception:
            # Artwork is disposable enrichment. Bibliographic resolution remains
            # successful even when image download/processing fails.
            pass
        finally:
            with self._lock:
                self._active.discard(cache_key)
            self._capacity.release()

    def close(self, *, wait: bool = True) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def __enter__(self) -> "ArtworkScheduler":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
