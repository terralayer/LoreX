from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from typing import Any

from benchmarks.importer_scenarios import PR6_SCENARIOS

PRODUCT_VERSION = "0.1.1 alpha"


def run_suite() -> dict[str, Any]:
    media = PR6_SCENARIOS["import_media_pipeline"](64, 2)
    queue = PR6_SCENARIOS["postgres_import_queue_claim"](250, 1)
    return {
        "schema_version": 1,
        "product_version": PRODUCT_VERSION,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "scenarios": [media, queue],
    }


def enforce_gates(report: dict[str, Any]) -> None:
    scenarios = {item["name"]: item for item in report["scenarios"]}
    media = scenarios["import_media_pipeline"]
    legacy = media["legacy_copy"]
    if media["bytes_copied"] != 0:
        raise RuntimeError("valid M4B preserve path must not copy payload bytes on the same filesystem")
    if legacy["bytes_copied"] <= media["bytes_copied"]:
        raise RuntimeError("PR6 preserve path must reduce payload copying versus legacy copy behavior")
    if legacy["temp_bytes_peak"] <= media["temp_bytes_peak"]:
        raise RuntimeError("PR6 preserve path must reduce temporary disk peak versus legacy copy behavior")
    if media["actions"]["preserve"] != media["scale"]:
        raise RuntimeError("valid M4B fixture must remain on the preserve path")
    if not scenarios["postgres_import_queue_claim"]["oldest_first"]:
        raise RuntimeError("import queue did not preserve oldest-first claim order")


def _markdown(report: dict[str, Any]) -> str:
    media, queue = report["scenarios"]
    legacy = media["legacy_copy"]
    disk_reduction = 1.0 - (media["temp_bytes_peak"] / legacy["temp_bytes_peak"])
    lines = [
        "# LoreX PR6 Importer and Media Pipeline Benchmark",
        "",
        f"- Product: `{report['product_version']}`",
        f"- Python: `{report['environment']['python']}`",
        "",
        "## Valid M4B preserve workload",
        "",
        f"- Imports: `{media['scale']}`",
        f"- Current p50/p95: `{media['timing']['p50_ms']:.3f}` / `{media['timing']['p95_ms']:.3f}` ms",
        f"- Current CPU sample: `{media['cpu_ms']:.3f}` ms",
        f"- Current temporary disk peak: `{media['temp_bytes_peak']}` bytes",
        f"- Current payload bytes copied: `{media['bytes_copied']}`",
        f"- Legacy copy p50/p95: `{legacy['p50_ms']:.3f}` / `{legacy['p95_ms']:.3f}` ms",
        f"- Legacy CPU sample: `{legacy['cpu_ms']:.3f}` ms",
        f"- Legacy temporary disk peak: `{legacy['temp_bytes_peak']}` bytes",
        f"- Legacy payload bytes copied: `{legacy['bytes_copied']}`",
        f"- Temporary disk reduction: `{disk_reduction:.3%}`",
        "",
        "## Durable import queue",
        "",
        f"- Jobs: `{queue['scale']}`",
        f"- p50/p95: `{queue['timing']['p50_ms']:.3f}` / `{queue['timing']['p95_ms']:.3f}` ms",
        f"- Oldest-first preserved: `{queue['oldest_first']}`",
        "",
        "The preserve fixture intentionally excludes external codec latency: valid M4B files are verified/tagged/promoted without FFmpeg re-encoding, while repair/extraction/FFmpeg concurrency is covered by correctness tests.",
        "",
    ]
    return "\n".join(lines)


def write_report(report: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "pr6-importer.json"
    markdown_path = output / "pr6-importer.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmark-results")
    args = parser.parse_args()
    report = run_suite()
    enforce_gates(report)
    _, markdown_path = write_report(report, args.output)
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
