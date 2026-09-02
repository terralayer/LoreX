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


def test_unknown_profile_is_rejected() -> None:
    runner = _runner_module()

    with pytest.raises(ValueError, match="unknown benchmark profile"):
        runner.run_suite("not-a-profile")
