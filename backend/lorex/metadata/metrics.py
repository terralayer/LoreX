from __future__ import annotations

from collections import Counter
from threading import RLock


class MetadataMetrics:
    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()
        self._providers: dict[str, Counter[str]] = {
            "upstream_requests": Counter(),
            "provider_retries": Counter(),
            "provider_failures": Counter(),
        }
        self._lock = RLock()

    def increment(self, name: str, *, provider: str | None = None, amount: int = 1) -> None:
        with self._lock:
            if provider is not None:
                self._providers.setdefault(name, Counter())[provider] += amount
            else:
                self._counters[name] += amount

    def snapshot(self) -> dict:
        with self._lock:
            result = dict(self._counters)
            for name in (
                "cache_hits",
                "cache_misses",
                "negative_cache_hits",
                "coalesced_followers",
                "local_fallbacks",
                "artwork_scheduled",
                "artwork_deduplicated",
                "artwork_dropped",
            ):
                result.setdefault(name, 0)
            for name, values in self._providers.items():
                result[name] = dict(values)
            return result
