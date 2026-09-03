from __future__ import annotations

from benchmarks.run_baseline import _PROFILE_CONFIGS
from benchmarks.scenarios import SCENARIOS


def test_pr5_benchmark_scenarios_are_registered() -> None:
    for name in (
        "queue_deque_roundtrip",
        "legacy_list_head_removal",
        "deque_head_removal",
        "postgres_queue_claim_transition",
        "streaming_downloader_memory",
        "streaming_downloader_throughput",
        "progress_coalescing",
    ):
        assert name in SCENARIOS


def test_ci_profile_runs_pr5_benchmarks() -> None:
    names = [name for name, _scale, _samples in _PROFILE_CONFIGS["ci"]]
    for name in (
        "queue_deque_roundtrip",
        "legacy_list_head_removal",
        "deque_head_removal",
        "postgres_queue_claim_transition",
        "streaming_downloader_memory",
        "streaming_downloader_throughput",
        "progress_coalescing",
    ):
        assert name in names
