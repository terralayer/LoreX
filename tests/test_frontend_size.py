from __future__ import annotations

import importlib

import pytest


def _frontend_size_module():
    try:
        return importlib.import_module("benchmarks.frontend_size")
    except ModuleNotFoundError as exc:
        pytest.fail(f"frontend size collector is not implemented yet: {exc}")


def test_collect_frontend_size_counts_files_bytes_and_gzip_deterministically(tmp_path) -> None:
    module = _frontend_size_module()
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_bytes(b"abc")
    (dist / "assets/app.js").write_bytes(b"hello")

    result = module.collect_frontend_size(dist)

    assert result["file_count"] == 2
    assert result["raw_bytes"] == 8
    assert result["gzip_bytes"] > 0
    assert result["files"] == [
        {"path": "assets/app.js", "raw_bytes": 5, "gzip_bytes": result["files"][0]["gzip_bytes"]},
        {"path": "index.html", "raw_bytes": 3, "gzip_bytes": result["files"][1]["gzip_bytes"]},
    ]
    assert all(item["gzip_bytes"] > 0 for item in result["files"])


def test_collect_frontend_size_requires_existing_directory(tmp_path) -> None:
    module = _frontend_size_module()

    with pytest.raises(FileNotFoundError):
        module.collect_frontend_size(tmp_path / "missing")
