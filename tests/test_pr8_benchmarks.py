from __future__ import annotations

import gzip

import pytest

from benchmarks.run_pr8 import enforce_gates
from benchmarks.ui_api import measure_entry_script


def _passing_report() -> dict:
    return {
        "dashboard": {"p95_ms": 80.0, "response_bytes": 120},
        "library_page": {"p95_ms": 40.0, "result_count": 50, "requested_limit": 50, "response_bytes": 6000},
        "frontend_entry": {
            "raw_bytes": 100_000,
            "gzip_bytes": 35_000,
            "path": "assets/index-entry.js",
            "lazy_js_files": 3,
        },
    }


def test_pr8_gates_accept_responsive_report():
    enforce_gates(_passing_report())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dashboard.p95_ms", 250.0),
        ("library_page.p95_ms", 100.0),
        ("library_page.result_count", 51),
        ("frontend_entry.raw_bytes", 151_610),
        ("frontend_entry.gzip_bytes", 48_670),
        ("frontend_entry.lazy_js_files", 0),
    ],
)
def test_pr8_gates_reject_budget_misses(field: str, value: float):
    report = _passing_report()
    section, key = field.split(".")
    report[section][key] = value
    with pytest.raises(RuntimeError):
        enforce_gates(report)


def test_measure_entry_script_counts_only_html_entry(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    entry = b"console.log('entry')" * 50
    lazy = b"console.log('lazy')" * 500
    (assets / "entry.js").write_bytes(entry)
    (assets / "HomePage.js").write_bytes(lazy)
    (assets / "LibraryPage.js").write_bytes(lazy)
    (tmp_path / "index.html").write_text(
        '<html><body><script type="module" crossorigin src="/assets/entry.js"></script></body></html>',
        encoding="utf-8",
    )

    result = measure_entry_script(tmp_path)

    assert result["path"] == "assets/entry.js"
    assert result["raw_bytes"] == len(entry)
    assert result["gzip_bytes"] == len(gzip.compress(entry, compresslevel=9, mtime=0))
    assert result["lazy_js_files"] == 2
