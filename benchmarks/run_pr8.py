from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.ui_api import run_ui_api_benchmarks

_PR1_ENTRY_RAW_BYTES = 151_610
_PR1_ENTRY_GZIP_BYTES = 48_670


def enforce_gates(report: dict) -> None:
    dashboard = report["dashboard"]
    library = report["library_page"]
    entry = report["frontend_entry"]

    if dashboard["p95_ms"] >= 250.0:
        raise RuntimeError(f"dashboard aggregate p95 must be <250 ms, got {dashboard['p95_ms']:.3f} ms")
    if library["p95_ms"] >= 100.0:
        raise RuntimeError(f"paged library read p95 must be <100 ms, got {library['p95_ms']:.3f} ms")
    if library["result_count"] > library["requested_limit"]:
        raise RuntimeError("paged library endpoint returned more rows than requested")
    if entry["raw_bytes"] >= _PR1_ENTRY_RAW_BYTES:
        raise RuntimeError(
            f"initial JavaScript entry must beat PR1 raw baseline {_PR1_ENTRY_RAW_BYTES}, got {entry['raw_bytes']}"
        )
    if entry["gzip_bytes"] >= _PR1_ENTRY_GZIP_BYTES:
        raise RuntimeError(
            f"initial JavaScript entry must beat PR1 gzip baseline {_PR1_ENTRY_GZIP_BYTES}, got {entry['gzip_bytes']}"
        )
    if entry["lazy_js_files"] < 1:
        raise RuntimeError("frontend build did not produce any lazy JavaScript chunks")


def _markdown(report: dict) -> str:
    dashboard = report["dashboard"]
    library = report["library_page"]
    entry = report["frontend_entry"]
    return "\n".join(
        [
            "# LoreX PR8 UI and API Responsiveness Benchmark",
            "",
            f"- Product: `{report['product_version']}`",
            f"- PostgreSQL releases: `{report['release_scale']:,}`",
            f"- PostgreSQL library books: `{report['library_scale']:,}`",
            f"- Download jobs: `{report['job_scale']:,}`",
            f"- Timed samples: `{report['samples']}`",
            "",
            "## Lightweight dashboard aggregate",
            "",
            f"- p50/p95: `{dashboard['p50_ms']:.3f}` / `{dashboard['p95_ms']:.3f}` ms",
            f"- Response payload: `{dashboard['response_bytes']:,}` bytes",
            f"- Peak Python allocation: `{dashboard['peak_python_mb']:.3f}` MiB",
            "",
            "## Paged library read",
            "",
            f"- p50/p95: `{library['p50_ms']:.3f}` / `{library['p95_ms']:.3f}` ms",
            f"- Page rows: `{library['result_count']}` / requested `{library['requested_limit']}`",
            f"- Offset: `{library['offset']:,}`",
            f"- Response payload: `{library['response_bytes']:,}` bytes",
            f"- Peak Python allocation: `{library['peak_python_mb']:.3f}` MiB",
            "",
            "## Frontend startup entry",
            "",
            f"- Entry: `{entry['path']}`",
            f"- Raw: `{entry['raw_bytes']:,}` bytes (PR1 primary JS baseline `{_PR1_ENTRY_RAW_BYTES:,}`)",
            f"- Deterministic gzip: `{entry['gzip_bytes']:,}` bytes (PR1 primary JS baseline `{_PR1_ENTRY_GZIP_BYTES:,}`)",
            f"- JavaScript files: `{entry['total_js_files']}` total / `{entry['lazy_js_files']}` lazy",
            "",
            "PR8 gates require dashboard p95 <250 ms, normal paged read p95 <100 ms, a bounded page response, a smaller initial JS entry than PR1, and at least one lazy chunk.",
            "",
        ]
    )


def write_report(report: dict, output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "pr8-ui-api.json"
    markdown_path = output / "pr8-ui-api.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmark-results")
    parser.add_argument("--frontend-dist", default="frontend/dist")
    parser.add_argument("--release-scale", type=int, default=100_000)
    parser.add_argument("--library-scale", type=int, default=100_000)
    parser.add_argument("--job-scale", type=int, default=1_000)
    parser.add_argument("--samples", type=int, default=20)
    args = parser.parse_args()

    report = run_ui_api_benchmarks(
        frontend_dist=args.frontend_dist,
        release_scale=args.release_scale,
        library_scale=args.library_scale,
        job_scale=args.job_scale,
        samples=args.samples,
    )
    enforce_gates(report)
    _, markdown_path = write_report(report, args.output)
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
