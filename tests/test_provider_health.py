from __future__ import annotations

from lorex.downloader.health import InMemoryProviderHealth


def test_provider_health_keeps_bounded_aggregate_counters() -> None:
    health = InMemoryProviderHealth()

    health.record("primary", success=True, fallback=False, byte_count=100, elapsed_ms=10.0)
    health.record("primary", success=False, fallback=True, byte_count=0, elapsed_ms=5.0)

    snapshot = health.snapshot("primary")
    assert snapshot.attempts == 2
    assert snapshot.successes == 1
    assert snapshot.failures == 1
    assert snapshot.fallbacks == 1
    assert snapshot.bytes_delivered == 100
    assert snapshot.elapsed_ms_total == 15.0
