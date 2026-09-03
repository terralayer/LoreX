from __future__ import annotations

import importlib
import json

import pytest


def _runner_module():
    try:
        return importlib.import_module("benchmarks.run_baseline")
    except ModuleNotFoundError as exc:
        pytest.fail(f"benchmark runner is not implemented yet: {exc}")


def test_smoke_suite_has_stable_schema_and_scenarios(tmp_path) -> None:
    runner = _runner_module()

    report = runner.run_suite("smoke")

    assert report["schema_version"] == 1
    assert report["product_version"] == "0.1.1 alpha"
    assert report["profile"] == "smoke"
    assert [scenario["name"] for scenario in report["scenarios"]] == [
        "index_headers",
        "group_and_classify",
        "release_search",
        "release_search_api",
        "queue_roundtrip",
        "mock_downloader",
        "library_importer",
        "postgres_bulk_index",
        "postgres_index_lookup",
        "postgres_release_search",
    ]
    for scenario in report["scenarios"]:
        assert scenario["scale"] > 0
        assert scenario["operation_count"] > 0
        assert scenario["throughput_per_sec"] >= 0
        assert scenario["timing"]["p50_ms"] >= 0
        assert scenario["timing"]["p95_ms"] >= scenario["timing"]["p50_ms"]

    json_path, markdown_path = runner.write_report(report, tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["profile"] == "smoke"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# LoreX Performance Baseline" in markdown
    assert "release_search" in markdown
    assert "library_importer" in markdown
    assert "postgres_bulk_index" in markdown
    assert "postgres_index_lookup" in markdown
    assert "postgres_release_search" in markdown


def test_frontend_build_size_is_embedded_in_json_and_markdown(tmp_path) -> None:
    runner = _runner_module()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "app.js").write_bytes(b"console.log('LoreX')")

    report = runner.run_suite("smoke")
    runner.attach_frontend_size(report, dist)
    json_path, markdown_path = runner.write_report(report, tmp_path / "report")

    persisted = json.loads(json_path.read_text(encoding="utf-8"))
    assert persisted["frontend"]["file_count"] == 1
    assert persisted["frontend"]["raw_bytes"] > 0
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "## Frontend Production Build" in markdown
    assert "Raw bytes" in markdown
    assert "Gzip bytes" in markdown


def test_unknown_profile_is_rejected() -> None:
    runner = _runner_module()

    with pytest.raises(ValueError, match="unknown benchmark profile"):
        runner.run_suite("not-a-profile")


def test_ci_gate_rejects_slow_million_release_search() -> None:
    runner = _runner_module()
    report = {
        "scenarios": [
            {
                "name": "postgres_release_search",
                "scale": 1_000_000,
                "timing": {"p95_ms": 150.0},
            }
        ]
    }

    with pytest.raises(RuntimeError, match="p95.*150"):
        runner.enforce_performance_gates(report)


def test_ci_gate_accepts_fast_million_release_search() -> None:
    runner = _runner_module()
    report = {
        "scenarios": [
            {
                "name": "postgres_release_search",
                "scale": 1_000_000,
                "timing": {"p95_ms": 149.999},
            }
        ]
    }

    runner.enforce_performance_gates(report)
