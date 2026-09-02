from benchmarks.run_baseline import _PROFILE_CONFIGS
from benchmarks.scenarios import SCENARIOS


def test_postgres_benchmark_scenarios_are_registered():
    assert "postgres_bulk_index" in SCENARIOS
    assert "postgres_index_lookup" in SCENARIOS


def test_ci_profile_runs_postgres_persistence_scenarios():
    names = [name for name, _scale, _samples in _PROFILE_CONFIGS["ci"]]
    assert "postgres_bulk_index" in names
    assert "postgres_index_lookup" in names
