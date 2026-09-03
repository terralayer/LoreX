from __future__ import annotations

from lorex.repository import JobRepository


def test_in_memory_provider_health_aggregates_are_bounded() -> None:
    repository = JobRepository()

    repository.record_provider_attempt("primary", success=True, fallback=False, byte_count=100, elapsed_ms=10.0)
    repository.record_provider_attempt("primary", success=False, fallback=True, byte_count=0, elapsed_ms=5.0)

    snapshot = repository.provider_health("primary")
    assert snapshot.attempts == 2
    assert snapshot.successes == 1
    assert snapshot.failures == 1
    assert snapshot.fallbacks == 1
    assert snapshot.bytes_delivered == 100
    assert snapshot.elapsed_ms_total == 15.0
