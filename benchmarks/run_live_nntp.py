from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.live_nntp_scenarios import run_live_nntp_benchmarks

_OVERVIEW_ROWS = 10_000
_BODY_BYTES = 64 * 1024 * 1024
_OVERVIEW_PEAK_MB = 32.0
_BODY_PEAK_MB = 8.0


def enforce_gates(report: dict) -> None:
    overview = report["overview"]
    body = report["body"]
    concurrency = report["provider_concurrency"]

    if overview["rows"] != _OVERVIEW_ROWS:
        raise RuntimeError(f"overview parser must consume {_OVERVIEW_ROWS:,} rows, got {overview['rows']:,}")
    if overview["peak_python_mb"] >= _OVERVIEW_PEAK_MB:
        raise RuntimeError(
            f"10K overview parsing peak Python allocation must be <{_OVERVIEW_PEAK_MB:.0f} MiB, "
            f"got {overview['peak_python_mb']:.3f} MiB"
        )
    if body["bytes"] != _BODY_BYTES:
        raise RuntimeError(f"BODY fixture must stream {_BODY_BYTES:,} bytes, got {body['bytes']:,}")
    if body["peak_python_mb"] >= _BODY_PEAK_MB:
        raise RuntimeError(
            f"64 MiB BODY streaming peak Python allocation must be <{_BODY_PEAK_MB:.0f} MiB, "
            f"got {body['peak_python_mb']:.3f} MiB"
        )
    if concurrency["observed_max"] > concurrency["configured_max"]:
        raise RuntimeError(
            "provider connection concurrency exceeded configured max_connections: "
            f"{concurrency['observed_max']} > {concurrency['configured_max']}"
        )


def _markdown(report: dict) -> str:
    overview = report["overview"]
    body = report["body"]
    concurrency = report["provider_concurrency"]
    return "\n".join(
        [
            "# LoreX Live NNTP Integration Benchmark",
            "",
            "## Overview parsing",
            "",
            f"- Rows: `{overview['rows']:,}`",
            f"- Elapsed: `{overview['elapsed_ms']:.3f}` ms",
            f"- Throughput: `{overview['rows_per_second']:,.1f}` rows/sec",
            f"- Peak Python allocation: `{overview['peak_python_mb']:.3f}` MiB",
            "",
            "## BODY streaming",
            "",
            f"- Bytes: `{body['bytes']:,}`",
            f"- Elapsed: `{body['elapsed_ms']:.3f}` ms",
            f"- Throughput: `{body['throughput_mib_s']:.1f}` MiB/sec",
            f"- Peak Python allocation: `{body['peak_python_mb']:.3f}` MiB",
            "",
            "## Provider concurrency",
            "",
            f"- Configured max_connections: `{concurrency['configured_max']}`",
            f"- Observed maximum: `{concurrency['observed_max']}`",
            f"- Concurrent requests exercised: `{concurrency['requests']}`",
            "",
            "Gates require 10K overview rows with <32 MiB peak Python allocation, "
            "a 64 MiB BODY stream with <8 MiB peak Python allocation, and observed "
            "provider concurrency no greater than configured max_connections.",
            "",
            "The transport fixtures are deterministic in-process benchmarks; they measure parser/streaming memory and concurrency behavior, not external Usenet network speed.",
            "",
        ]
    )


def write_report(report: dict, output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "live-nntp.json"
    markdown_path = output / "live-nntp.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmark-results")
    args = parser.parse_args()

    report = run_live_nntp_benchmarks()
    enforce_gates(report)
    _, markdown_path = write_report(report, args.output)
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
