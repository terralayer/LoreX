from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from redis import Redis

from lorex.metadata.cache import InMemoryMetadataCache
from lorex.metadata.metrics import MetadataMetrics
from lorex.metadata.model import BookMetadata, MetadataLookup, ProviderOutcome
from lorex.metadata.providers import ProviderError
from lorex.metadata.redis_cache import RedisLeaseCoordinator, RedisMetadataCache
from lorex.metadata.resolver import MetadataResolver


class CountingProvider:
    name = "fake"

    def __init__(self, *, delay: float = 0.02, outcome: ProviderOutcome | None = None) -> None:
        self.delay = delay
        self.outcome = outcome or ProviderOutcome.found(
            BookMetadata(title="Project Hail Mary", authors=("Andy Weir",), source=self.name)
        )
        self.calls = 0
        self._lock = threading.Lock()

    def lookup(self, lookup: MetadataLookup) -> ProviderOutcome:
        with self._lock:
            self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return self.outcome


class FailThenSucceedProvider:
    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    def lookup(self, lookup: MetadataLookup) -> ProviderOutcome:
        self.calls += 1
        if self.calls == 1:
            raise ProviderError(self.name, "temporary", transient=True)
        return ProviderOutcome.found(BookMetadata(title="Recovered", source=self.name))


class AlwaysFailProvider:
    name = "down"

    def __init__(self) -> None:
        self.calls = 0

    def lookup(self, lookup: MetadataLookup) -> ProviderOutcome:
        self.calls += 1
        raise ProviderError(self.name, "temporary", transient=True)


def test_one_hundred_same_key_callers_share_one_upstream_request():
    provider = CountingProvider()
    metrics = MetadataMetrics()
    resolver = MetadataResolver(
        cache=InMemoryMetadataCache(),
        providers=(provider,),
        metrics=metrics,
    )
    lookup = MetadataLookup(isbn13="9780063279327")

    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(lambda _: resolver.resolve(lookup), range(100)))

    assert provider.calls == 1
    assert all(result is not None and result.title == "Project Hail Mary" for result in results)
    snapshot = metrics.snapshot()
    assert snapshot["upstream_requests"]["fake"] == 1
    assert snapshot["coalesced_followers"] >= 1
    assert snapshot["cache_hits"] >= 99


def test_negative_cache_prevents_repeated_not_found_requests():
    provider = CountingProvider(delay=0, outcome=ProviderOutcome.not_found())
    metrics = MetadataMetrics()
    resolver = MetadataResolver(cache=InMemoryMetadataCache(), providers=(provider,), metrics=metrics)
    lookup = MetadataLookup(title="Missing Book", authors=("Nobody",))

    assert resolver.resolve(lookup) is None
    assert resolver.resolve(lookup) is None

    assert provider.calls == 1
    assert metrics.snapshot()["negative_cache_hits"] == 1


def test_transient_failure_is_not_negative_cached_and_later_call_retries():
    provider = FailThenSucceedProvider()
    resolver = MetadataResolver(cache=InMemoryMetadataCache(), providers=(provider,))
    lookup = MetadataLookup(title="Recovered", authors=("Author",))

    assert resolver.resolve(lookup) is None
    recovered = resolver.resolve(lookup)

    assert provider.calls == 2
    assert recovered is not None
    assert recovered.title == "Recovered"


def test_local_metadata_survives_external_provider_failure():
    provider = AlwaysFailProvider()
    metrics = MetadataMetrics()
    resolver = MetadataResolver(cache=InMemoryMetadataCache(), providers=(provider,), metrics=metrics)
    lookup = MetadataLookup(title="Local Title", authors=("Local Author",))
    local = BookMetadata(title="Local Title", authors=("Local Author",), source="local", confidence=0.6)

    result = resolver.resolve(lookup, local_metadata=local)

    assert result == local
    assert metrics.snapshot()["local_fallbacks"] == 1


def test_safe_not_found_can_return_local_metadata_while_caching_negative_result():
    provider = CountingProvider(delay=0, outcome=ProviderOutcome.not_found())
    resolver = MetadataResolver(cache=InMemoryMetadataCache(), providers=(provider,))
    lookup = MetadataLookup(title="Local Title", authors=("Local Author",))
    local = BookMetadata(title="Local Title", authors=("Local Author",), source="local")

    assert resolver.resolve(lookup, local_metadata=local) == local
    assert resolver.resolve(lookup, local_metadata=local) == local
    assert provider.calls == 1


def test_two_resolver_instances_share_one_upstream_request_through_redis():
    client = Redis.from_url(os.environ["LOREX_REDIS_URL"], decode_responses=True)
    client.flushdb()
    provider = CountingProvider(delay=0.05)
    cache_a = RedisMetadataCache(client)
    cache_b = RedisMetadataCache(client)
    metrics_a = MetadataMetrics()
    metrics_b = MetadataMetrics()
    resolver_a = MetadataResolver(
        cache=cache_a,
        providers=(provider,),
        lease_coordinator=RedisLeaseCoordinator(client, lease_ttl=5),
        metrics=metrics_a,
        follower_wait=2.0,
        poll_interval=0.005,
    )
    resolver_b = MetadataResolver(
        cache=cache_b,
        providers=(provider,),
        lease_coordinator=RedisLeaseCoordinator(client, lease_ttl=5),
        metrics=metrics_b,
        follower_wait=2.0,
        poll_interval=0.005,
    )
    lookup = MetadataLookup(isbn13="9780063279327")
    resolvers = (resolver_a, resolver_b)

    def resolve(index: int) -> BookMetadata | None:
        return resolvers[index % 2].resolve(lookup)

    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(resolve, range(100)))

    assert provider.calls == 1
    assert all(result is not None and result.title == "Project Hail Mary" for result in results)
    assert metrics_a.snapshot()["coalesced_followers"] + metrics_b.snapshot()["coalesced_followers"] >= 1
