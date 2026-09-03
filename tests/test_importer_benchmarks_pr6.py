from __future__ import annotations

from benchmarks.importer_scenarios import PR6_SCENARIOS


def test_pr6_import_pipeline_benchmark_reports_resource_and_action_metrics() -> None:
    scenario = PR6_SCENARIOS["import_media_pipeline"](2, 1)

    assert scenario["name"] == "import_media_pipeline"
    assert scenario["scale"] == 2
    assert scenario["cpu_ms"] >= 0
    assert scenario["temp_bytes_peak"] > 0
    assert scenario["bytes_copied"] == 0
    assert scenario["actions"] == {"preserve": 2, "remux": 0, "transcode": 0}
    assert scenario["legacy_copy"]["bytes_copied"] == 2 * 64 * 1024
    assert scenario["legacy_copy"]["temp_bytes_peak"] > scenario["temp_bytes_peak"]
    assert scenario["timing"]["p95_ms"] >= scenario["timing"]["p50_ms"]


def test_pr6_import_queue_benchmark_records_oldest_first_claims() -> None:
    scenario = PR6_SCENARIOS["postgres_import_queue_claim"](10, 1)

    assert scenario["name"] == "postgres_import_queue_claim"
    assert scenario["scale"] == 10
    assert scenario["oldest_first"] is True
