from __future__ import annotations

import platform
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from redis import Redis

from benchmarks.metrics import percentile
from lorex.metadata.cache import InMemoryMetadataCache
from lorex.metadata.metrics import MetadataMetrics
from lorex.metadata.model import BookMetadata, MetadataLookup, ProviderOutcome
from lorex.metadata.redis_cache import RedisLeaseCoordinator, RedisMetadataCache
from lorex.metadata.resolver import MetadataResolver

PRODUCT_VERSION = "0.1.1 alpha"


class FakeLatencyProvider:
    name = "fake_metadata"

    def __init__(self, *, delay: float, outcome: ProviderOutcome) -> None:
        self.delay = delay
        self.outcome = outcome
        self.calls = 0
        self._lock = threading.Lock()

    def lookup(self, lookup: MetadataLookup) -> ProviderOutcome:
        with self._lock:
            self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return self.outcome


@dataclass(frozen=True, slots=True)
class BurstResult:
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    completed: int


def _burst(call: Callable[[int], BookMetadata | None], consumers: int) -> BurstResult:
    if consumers < 1:
        raise ValueError("consumers must be at least 1")

    durations: list[float] = []
    durations_lock = threading.Lock()

    def timed(index: int) -> BookMetadata | None:
        started = time.perf_counter()
        result = call(index)
        elapsed_ms = (time.perf_counter() - started) * 1000
        with durations_lock:
            durations.append(elapsed_ms)
        return result

    with ThreadPoolExecutor(max_workers=min(32, consumers)) as executor:
        results = list(executor.map(timed, range(consumers)))

    if len(durations) != consumers:
        raise RuntimeError("metadata benchmark did not record every consumer")
    return BurstResult(
        p50_ms=percentile(durations, 0.50),
        p95_ms=percentile(durations, 0.95),
        min_ms=min(durations),
        max_ms=max(durations),
        completed=sum(result is not None for result in results),
    )


def _timing_fields(result: BurstResult) -> dict[str, float | int]:
    return {
        "p50_ms": result.p50_ms,
        "p95_ms": result.p95_ms,
        "min_ms": result.min_ms,
        "max_ms": result.max_ms,
        "completed": result.completed,
    }


def run_metadata_benchmarks(
    *,
    consumers: int = 100,
    provider_delay: float = 0.05,
    redis_url: str | None = None,
) -> dict:
    if consumers < 1:
        raise ValueError("consumers must be at least 1")
    if provider_delay <= 0:
        raise ValueError("provider_delay must be positive")

    lookup = MetadataLookup(isbn13="9780063279327")
    metadata = BookMetadata(
        title="Project Hail Mary",
        authors=("Andy Weir",),
        source=FakeLatencyProvider.name,
        isbn13="9780063279327",
    )

    found_provider = FakeLatencyProvider(
        delay=provider_delay,
        outcome=ProviderOutcome.found(metadata),
    )
    found_metrics = MetadataMetrics()
    found_resolver = MetadataResolver(
        cache=InMemoryMetadataCache(),
        providers=(found_provider,),
        metrics=found_metrics,
    )

    cold = _burst(lambda _: found_resolver.resolve(lookup), consumers)
    cold_snapshot = found_metrics.snapshot()
    cold_scenario = {
        "name": "metadata_cold_same_key",
        "consumers": consumers,
        **_timing_fields(cold),
        "upstream_calls": found_provider.calls,
        "coalesced_followers": cold_snapshot["coalesced_followers"],
        "cache_hits": cold_snapshot["cache_hits"],
    }

    calls_before_warm = found_provider.calls
    warm = _burst(lambda _: found_resolver.resolve(lookup), consumers)
    warm_snapshot = found_metrics.snapshot()
    warm_scenario = {
        "name": "metadata_warm_cache",
        "consumers": consumers,
        **_timing_fields(warm),
        "additional_upstream_calls": found_provider.calls - calls_before_warm,
        "total_upstream_calls": found_provider.calls,
        "cache_hits": warm_snapshot["cache_hits"],
    }

    not_found_provider = FakeLatencyProvider(
        delay=provider_delay,
        outcome=ProviderOutcome.not_found(),
    )
    negative_metrics = MetadataMetrics()
    negative_resolver = MetadataResolver(
        cache=InMemoryMetadataCache(),
        providers=(not_found_provider,),
        metrics=negative_metrics,
    )
    negative_lookup = MetadataLookup(title="Missing Book", authors=("Nobody",))
    negative_resolver.resolve(negative_lookup)
    negative_calls_before = not_found_provider.calls
    negative = _burst(lambda _: negative_resolver.resolve(negative_lookup), consumers)
    negative_snapshot = negative_metrics.snapshot()
    negative_scenario = {
        "name": "metadata_negative_cache",
        "consumers": consumers,
        **_timing_fields(negative),
        "total_upstream_calls": not_found_provider.calls,
        "additional_upstream_calls": not_found_provider.calls - negative_calls_before,
        "negative_cache_hits": negative_snapshot["negative_cache_hits"],
    }

    shared_scenario: dict[str, object]
    if redis_url:
        client = Redis.from_url(redis_url, decode_responses=True)
        client.flushdb()
        shared_provider = FakeLatencyProvider(
            delay=provider_delay,
            outcome=ProviderOutcome.found(metadata),
        )
        metrics_a = MetadataMetrics()
        metrics_b = MetadataMetrics()
        resolver_a = MetadataResolver(
            cache=RedisMetadataCache(client),
            providers=(shared_provider,),
            lease_coordinator=RedisLeaseCoordinator(client, lease_ttl=5),
            metrics=metrics_a,
            follower_wait=2.0,
            poll_interval=0.005,
        )
        resolver_b = MetadataResolver(
            cache=RedisMetadataCache(client),
            providers=(shared_provider,),
            lease_coordinator=RedisLeaseCoordinator(client, lease_ttl=5),
            metrics=metrics_b,
            follower_wait=2.0,
            poll_interval=0.005,
        )
        resolvers = (resolver_a, resolver_b)
        shared = _burst(lambda index: resolvers[index % 2].resolve(lookup), consumers)
        snapshot_a = metrics_a.snapshot()
        snapshot_b = metrics_b.snapshot()
        shared_scenario = {
            "name": "metadata_shared_redis",
            "consumers": consumers,
            **_timing_fields(shared),
            "upstream_calls": shared_provider.calls,
            "coalesced_followers": (
                snapshot_a["coalesced_followers"] + snapshot_b["coalesced_followers"]
            ),
            "skipped": False,
        }
    else:
        shared_scenario = {
            "name": "metadata_shared_redis",
            "consumers": consumers,
            "upstream_calls": 0,
            "coalesced_followers": 0,
            "skipped": True,
            "reason": "LOREX_REDIS_URL not configured",
        }

    return {
        "schema_version": 1,
        "product_version": PRODUCT_VERSION,
        "provider_delay_ms": provider_delay * 1000,
        "consumers": consumers,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "scenarios": [cold_scenario, warm_scenario, negative_scenario, shared_scenario],
    }
