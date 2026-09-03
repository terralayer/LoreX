from __future__ import annotations

import threading
import time
from collections.abc import Iterable
from typing import Protocol

from lorex.metadata.cache import InMemoryMetadataCache, MetadataCache
from lorex.metadata.metrics import MetadataMetrics
from lorex.metadata.model import BookMetadata, MetadataLookup, normalize_lookup_key
from lorex.metadata.providers import MetadataProvider, ProviderError


class LeaseLike(Protocol):
    def release(self) -> None: ...


class LeaseCoordinator(Protocol):
    def acquire(self, lookup_key: str) -> LeaseLike | None: ...


class ArtworkSchedulerLike(Protocol):
    def submit(self, cache_key: str, url: str) -> bool: ...


class MetadataResolver:
    def __init__(
        self,
        *,
        cache: MetadataCache,
        providers: Iterable[MetadataProvider],
        lease_coordinator: LeaseCoordinator | None = None,
        metrics: MetadataMetrics | None = None,
        artwork_scheduler: ArtworkSchedulerLike | None = None,
        follower_wait: float = 20.0,
        poll_interval: float = 0.02,
        sleeper=time.sleep,
        clock=time.monotonic,
    ) -> None:
        if follower_wait <= 0 or poll_interval <= 0:
            raise ValueError("follower wait and poll interval must be positive")
        self.cache = cache
        self.providers = tuple(providers)
        self.lease_coordinator = lease_coordinator
        self.metrics = metrics or MetadataMetrics()
        self.artwork_scheduler = artwork_scheduler
        self.follower_wait = follower_wait
        self.poll_interval = poll_interval
        self.sleeper = sleeper
        self.clock = clock
        self._fallback_cache = InMemoryMetadataCache()
        self._key_locks: dict[str, threading.Lock] = {}
        self._key_locks_guard = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._key_locks_guard:
            return self._key_locks.setdefault(key, threading.Lock())

    def _get_entry(self, key: str):
        try:
            entry = self.cache.get(key)
        except Exception:
            entry = self._fallback_cache.get(key)
        if entry is None:
            return None
        return entry

    def _read_cached(self, key: str, *, count_miss: bool = True) -> tuple[bool, BookMetadata | None]:
        entry = self._get_entry(key)
        if entry is None:
            if count_miss:
                self.metrics.increment("cache_misses")
            return False, None
        if entry.status == "not_found":
            self.metrics.increment("negative_cache_hits")
            return True, None
        self.metrics.increment("cache_hits")
        return True, entry.metadata

    def _set_found(self, key: str, metadata: BookMetadata) -> None:
        self._fallback_cache.set_found(key, metadata)
        try:
            self.cache.set_found(key, metadata)
        except Exception:
            pass

    def _set_not_found(self, key: str) -> None:
        self._fallback_cache.set_not_found(key)
        try:
            self.cache.set_not_found(key)
        except Exception:
            pass

    def _schedule_artwork(self, key: str, metadata: BookMetadata) -> None:
        if self.artwork_scheduler is None or not metadata.artwork_url:
            return
        try:
            accepted = self.artwork_scheduler.submit(key, metadata.artwork_url)
        except Exception:
            self.metrics.increment("artwork_dropped")
            return
        self.metrics.increment("artwork_scheduled" if accepted else "artwork_deduplicated")

    def _lookup_providers(
        self,
        key: str,
        lookup: MetadataLookup,
        local_metadata: BookMetadata | None,
    ) -> BookMetadata | None:
        saw_error = False
        for provider in self.providers:
            self.metrics.increment("upstream_requests", provider=provider.name)
            try:
                outcome = provider.lookup(lookup)
            except ProviderError:
                saw_error = True
                self.metrics.increment("provider_failures", provider=provider.name)
                continue
            except Exception:
                saw_error = True
                self.metrics.increment("provider_failures", provider=provider.name)
                continue

            if outcome.status == "found" and outcome.metadata is not None:
                self._set_found(key, outcome.metadata)
                self._schedule_artwork(key, outcome.metadata)
                return outcome.metadata

        if not saw_error:
            self._set_not_found(key)
        if local_metadata is not None:
            self.metrics.increment("local_fallbacks")
            return local_metadata
        return None

    def _leader_lookup(
        self,
        key: str,
        lookup: MetadataLookup,
        local_metadata: BookMetadata | None,
        lease: LeaseLike | None,
    ) -> BookMetadata | None:
        try:
            return self._lookup_providers(key, lookup, local_metadata)
        finally:
            if lease is not None:
                try:
                    lease.release()
                except Exception:
                    pass

    def _wait_for_leader(
        self,
        key: str,
        lookup: MetadataLookup,
        local_metadata: BookMetadata | None,
    ) -> BookMetadata | None:
        self.metrics.increment("coalesced_followers")
        deadline = self.clock() + self.follower_wait
        while self.clock() < deadline:
            cached, result = self._read_cached(key, count_miss=False)
            if cached:
                return local_metadata if result is None and local_metadata is not None else result
            self.sleeper(self.poll_interval)

            if self.lease_coordinator is not None:
                try:
                    lease = self.lease_coordinator.acquire(key)
                except Exception:
                    lease = None
                    break
                if lease is not None:
                    cached, result = self._read_cached(key, count_miss=False)
                    if cached:
                        try:
                            lease.release()
                        except Exception:
                            pass
                        return local_metadata if result is None and local_metadata is not None else result
                    return self._leader_lookup(key, lookup, local_metadata, lease)

        if local_metadata is not None:
            self.metrics.increment("local_fallbacks")
            return local_metadata
        return None

    def resolve(
        self,
        lookup: MetadataLookup,
        *,
        local_metadata: BookMetadata | None = None,
    ) -> BookMetadata | None:
        key = normalize_lookup_key(lookup)
        cached, result = self._read_cached(key)
        if cached:
            return local_metadata if result is None and local_metadata is not None else result

        lock = self._lock_for(key)
        with lock:
            cached, result = self._read_cached(key, count_miss=False)
            if cached:
                self.metrics.increment("coalesced_followers")
                return local_metadata if result is None and local_metadata is not None else result

            if self.lease_coordinator is None:
                return self._leader_lookup(key, lookup, local_metadata, None)

            try:
                lease = self.lease_coordinator.acquire(key)
            except Exception:
                # Redis is an accelerator. A process-local lock remains sufficient
                # to avoid duplicate work inside this worker when Redis is down.
                return self._leader_lookup(key, lookup, local_metadata, None)

            if lease is not None:
                return self._leader_lookup(key, lookup, local_metadata, lease)
            return self._wait_for_leader(key, lookup, local_metadata)
