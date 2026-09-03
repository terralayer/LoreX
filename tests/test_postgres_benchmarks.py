from benchmarks.run_baseline import _PROFILE_CONFIGS
from benchmarks.scenarios import SCENARIOS


def test_postgres_benchmark_scenarios_are_registered():
    assert "postgres_bulk_index" in SCENARIOS
    assert "postgres_index_lookup" in SCENARIOS
    assert "postgres_release_search" in SCENARIOS


def test_ci_profile_runs_postgres_persistence_scenarios():
    names = [name for name, _scale, _samples in _PROFILE_CONFIGS["ci"]]
    assert "postgres_bulk_index" in names
    assert "postgres_index_lookup" in names
    assert ("postgres_release_search", 100_000, 10) in _PROFILE_CONFIGS["ci"]
    assert ("postgres_release_search", 1_000_000, 10) in _PROFILE_CONFIGS["ci"]
