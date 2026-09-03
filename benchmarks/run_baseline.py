from __future__ import annotations

import argparse
import gc
import json
import platform
from pathlib import Path
from typing import Any

from benchmarks.frontend_size import collect_frontend_size
from benchmarks.scenarios import SCENARIOS

PRODUCT_VERSION = "0.1.1 alpha"
POSTGRES_MILLION_SEARCH_P95_LIMIT_MS = 150.0
QUEUE_DEQUE_10K_P95_LIMIT_MS = 107.0
STREAMING_64MIB_PEAK_PYTHON_LIMIT_MB = 16.0
PROGRESS_WRITE_REDUCTION_MIN = 0.90

_PROFILE_CONFIGS: dict[str, list[tuple[str, int, int]]] = {
    "smoke": [
        ("index_headers", 30, 1),
        ("group_and_classify", 30, 1),
        ("release_search", 100, 2),
        ("release_search_api", 100, 2),
        ("queue_roundtrip", 20, 1),
        ("queue_deque_roundtrip", 1_000, 1),
        ("mock_downloader", 20, 1),
        ("library_importer", 20, 1),
        ("postgres_bulk_index", 100, 1),
        ("postgres_index_lookup", 1_000, 3),
        ("postgres_release_search", 1_000, 3),
        ("postgres_queue_claim_transition", 50, 1),
        ("streaming_downloader_memory", 4, 1),
        ("streaming_downloader_throughput", 4, 1),
        ("progress_coalescing", 1_000, 1),
    ],
    "ci": [
        ("index_headers", 10_000, 2),
        ("index_headers", 100_000, 1),
        ("group_and_classify", 10_000, 2),
        ("group_and_classify", 100_000, 1),
        ("release_search", 10_000, 5),
        ("release_search", 100_000, 5),
        ("release_search", 1_000_000, 3),
        ("release_search_api", 10_000, 5),
        ("release_search_api", 100_000, 3),
        ("queue_roundtrip", 10_000, 2),
        ("queue_deque_roundtrip", 10_000, 3),
        ("mock_downloader", 10_000, 2),
        ("library_importer", 10_000, 2),
        ("postgres_bulk_index", 10_000, 1),
        ("postgres_index_lookup", 10_000, 10),
        ("postgres_release_search", 100_000, 10),
        ("postgres_release_search", 1_000_000, 10),
        ("postgres_queue_claim_transition", 1_000, 1),
        ("streaming_downloader_memory", 64, 1),
        ("streaming_downloader_throughput", 64, 2),
        ("progress_coalescing", 10_000, 3),
    ],
}


def enforce_performance_gates(report: dict[str, Any]) -> None:
    for scenario in report["scenarios"]:
        name = scenario["name"]
        scale = scenario["scale"]
        if name == "postgres_release_search" and scale == 1_000_000:
            p95_ms = scenario["timing"]["p95_ms"]
            if p95_ms >= POSTGRES_MILLION_SEARCH_P95_LIMIT_MS:
                raise RuntimeError(
                    f"postgres_release_search p95 {p95_ms:.3f} ms must be below "
                    f"{POSTGRES_MILLION_SEARCH_P95_LIMIT_MS:.0f} ms at 1,000,000 releases"
                )
        if name == "queue_deque_roundtrip" and scale == 10_000:
            p95_ms = scenario["timing"]["p95_ms"]
            if p95_ms >= QUEUE_DEQUE_10K_P95_LIMIT_MS:
                raise RuntimeError(
                    f"queue_deque_roundtrip p95 {p95_ms:.3f} ms must improve on the "
                    f"PR1 10,000-job reference of {QUEUE_DEQUE_10K_P95_LIMIT_MS:.0f} ms"
                )
        if name == "streaming_downloader_memory" and scale == 64:
            peak_python_mb = scenario["timing"]["peak_python_mb"]
            if peak_python_mb >= STREAMING_64MIB_PEAK_PYTHON_LIMIT_MB:
                raise RuntimeError(
                    f"streaming_downloader_memory peak Python allocation {peak_python_mb:.3f} MiB "
                    f"must stay below {STREAMING_64MIB_PEAK_PYTHON_LIMIT_MB:.0f} MiB for a 64 MiB payload"
                )
        if name == "progress_coalescing" and scale == 10_000:
            reduction = scenario["write_reduction_ratio"]
            if reduction < PROGRESS_WRITE_REDUCTION_MIN:
                raise RuntimeError(
                    f"progress_coalescing write reduction {reduction:.3%} must be at least "
                    f"{PROGRESS_WRITE_REDUCTION_MIN:.0%}"
                )


def run_suite(profile: str) -> dict[str, Any]:
    config = _PROFILE_CONFIGS.get(profile)
    if config is None:
        raise ValueError(f"unknown benchmark profile: {profile}")

    scenarios: list[dict[str, Any]] = []
    for name, scale, samples in config:
        scenarios.append(SCENARIOS[name](scale, samples))
        gc.collect()

    report = {
        "schema_version": 1,
        "product_version": PRODUCT_VERSION,
        "profile": profile,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "scenarios": scenarios,
        "notes": [
            "Synthetic data is generated deterministically from fixed seeds.",
            "The historical PR1 10,000-job queue p95 reference is retained as the PR5 improvement comparison.",
            "PR5 queue claims remain durable PostgreSQL rows rather than destructive dequeues.",
            "Streaming downloader throughput uses a zero-delay synthetic provider so provider/network latency is excluded.",
            "Streaming memory measurements use fixed 64 KiB chunks and bounded article/provider concurrency.",
            "Progress persistence measurements distinguish logical progress events from actual persistence writes.",
            "PostgreSQL search fixtures are seeded outside measured query latency using set-based SQL.",
        ],
    }
    return report


def attach_frontend_size(report: dict[str, Any], dist: str | Path) -> dict[str, Any]:
    report["frontend"] = collect_frontend_size(dist)
    return report


def _markdown(report: dict[str, Any]) -> str:
    environment = report["environment"]
    lines = [
        "# LoreX Performance Baseline",
        "",
        f"- Product: `{report['product_version']}`",
        f"- Profile: `{report['profile']}`",
        f"- Python: `{environment['python']}`",
        f"- Platform: `{environment['platform']}`",
        f"- Machine: `{environment['machine']}`",
        "",
        "| Scenario | Scale | Unit | p50 ms | p95 ms | Mean ms | Ops/sec | Peak Python MB | Peak RSS MB |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario in report["scenarios"]:
        timing = scenario["timing"]
        lines.append(
            "| {name} | {scale:,} | {unit} | {p50:.3f} | {p95:.3f} | {mean:.3f} | {throughput:,.1f} | {python_mb:.2f} | {rss_mb:.2f} |".format(
                name=scenario["name"],
                scale=scenario["scale"],
                unit=scenario["unit"],
                p50=timing["p50_ms"],
                p95=timing["p95_ms"],
                mean=timing["mean_ms"],
                throughput=scenario["throughput_per_sec"],
                python_mb=timing["peak_python_mb"],
                rss_mb=timing["peak_rss_mb"],
            )
        )
        if scenario.get("note"):
            lines.append(f"\n> **{scenario['name']} note:** {scenario['note']}")
        if scenario["name"] == "progress_coalescing":
            lines.append(
                f"> Persistence writes: `{scenario['persistence_writes']}`; "
                f"write reduction: `{scenario['write_reduction_ratio']:.3%}`."
            )

    frontend = report.get("frontend")
    if frontend is not None:
        lines.extend(
            [
                "",
                "## Frontend Production Build",
                "",
                f"- Files: `{frontend['file_count']}`",
                f"- Raw bytes: `{frontend['raw_bytes']}`",
                f"- Gzip bytes: `{frontend['gzip_bytes']}`",
            ]
        )

    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in report["notes"])
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "baseline.json"
    markdown_path = output / "baseline.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the LoreX performance baseline suite")
    parser.add_argument("--profile", choices=sorted(_PROFILE_CONFIGS), default="smoke")
    parser.add_argument("--output", default="benchmark-results")
    parser.add_argument("--frontend-dist")
    args = parser.parse_args()

    report = run_suite(args.profile)
    if args.frontend_dist:
        attach_frontend_size(report, args.frontend_dist)
    json_path, markdown_path = write_report(report, args.output)
    print(markdown_path.read_text(encoding="utf-8"))
    print(f"JSON report: {json_path}")
    if args.profile == "ci":
        enforce_performance_gates(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
