import os

from benchmarks.metadata import run_metadata_benchmarks
from benchmarks.run_pr7 import enforce_gates


def test_metadata_benchmark_proves_coalescing_cache_and_negative_cache():
    report = run_metadata_benchmarks(
        consumers=100,
        provider_delay=0.05,
        redis_url=os.environ.get("LOREX_REDIS_URL"),
    )
    scenarios = {scenario["name"]: scenario for scenario in report["scenarios"]}

    cold = scenarios["metadata_cold_same_key"]
    warm = scenarios["metadata_warm_cache"]
    negative = scenarios["metadata_negative_cache"]

    assert cold["consumers"] == 100
    assert cold["upstream_calls"] == 1
    assert cold["coalesced_followers"] >= 1
    assert warm["additional_upstream_calls"] == 0
    assert warm["p95_ms"] < 25.0
    assert negative["total_upstream_calls"] == 1
    assert negative["additional_upstream_calls"] == 0
    assert negative["negative_cache_hits"] >= 100

    shared = scenarios["metadata_shared_redis"]
    assert shared["consumers"] == 100
    assert shared["upstream_calls"] == 1

    enforce_gates(report)
