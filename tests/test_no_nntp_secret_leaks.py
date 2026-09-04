from __future__ import annotations

import json
from pathlib import Path

from benchmarks.live_nntp_scenarios import FAKE_PASSWORD, FAKE_USERNAME
from benchmarks.run_live_nntp import _markdown, enforce_gates


def _sample_report() -> dict:
    return {
        "overview": {
            "rows": 10_000,
            "peak_python_mb": 4.0,
            "elapsed_ms": 20.0,
            "rows_per_second": 500_000.0,
        },
        "body": {
            "bytes": 64 * 1024 * 1024,
            "peak_python_mb": 2.0,
            "elapsed_ms": 320.0,
            "throughput_mib_s": 200.0,
        },
        "provider_concurrency": {
            "configured_max": 4,
            "observed_max": 4,
            "requests": 24,
        },
    }


def test_live_nntp_benchmark_gates_accept_bounded_report() -> None:
    enforce_gates(_sample_report())


def test_benchmark_reports_never_render_fake_credentials(tmp_path: Path) -> None:
    report = _sample_report()
    report["provider"] = {
        "host": "news.example.test",
        "username_configured": True,
        "password_configured": True,
    }
    markdown = _markdown(report)
    json_text = json.dumps(report, sort_keys=True)
    combined = markdown + json_text
    assert FAKE_USERNAME not in combined
    assert FAKE_PASSWORD not in combined


def test_ci_uses_generated_test_key_not_a_repository_key() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "LOREX_CREDENTIAL_KEY" in workflow
    assert "credential-test-key" not in workflow.casefold()
    assert FAKE_PASSWORD not in workflow
