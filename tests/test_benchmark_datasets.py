from __future__ import annotations

import importlib

import pytest


def _datasets_module():
    try:
        return importlib.import_module("benchmarks.datasets")
    except ModuleNotFoundError as exc:
        pytest.fail(f"benchmark dataset module is not implemented yet: {exc}")


def test_header_generation_is_exact_and_seed_deterministic() -> None:
    datasets = _datasets_module()

    first = datasets.generate_headers(7, seed=42)
    second = datasets.generate_headers(7, seed=42)
    different = datasets.generate_headers(7, seed=43)

    assert len(first) == 7
    assert first == second
    assert first != different
    assert first[0].message_id.startswith("<bench-42-")
    assert first[0].subject.endswith("[1/3]")


def test_release_population_has_deterministic_tail_search_needle() -> None:
    datasets = _datasets_module()

    first = datasets.populate_releases(25, seed=42)
    second = datasets.populate_releases(25, seed=42)

    first_ids = list(first._items)
    second_ids = list(second._items)
    assert first_ids == second_ids
    assert len(first_ids) == 25

    results = first.search(datasets.search_term(42))
    assert len(results) == 1
    assert results[0].title == datasets.search_term(42)
    assert results[0].id == first_ids[-1]


def test_job_and_download_result_generation_has_exact_counts() -> None:
    datasets = _datasets_module()

    jobs = datasets.populate_jobs(11)
    downloads = datasets.generate_download_results(13, seed=42)

    assert len(jobs._items) == 11
    assert len(downloads) == 13
    assert downloads == datasets.generate_download_results(13, seed=42)
