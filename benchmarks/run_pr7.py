from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from benchmarks.metadata import run_metadata_benchmarks


def enforce_gates(report: dict) -> None:
    scenarios = {item["name"]: item for item in report["scenarios"]}
    cold = scenarios["metadata_cold_same_key"]
    warm = scenarios["metadata_warm_cache"]
    negative = scenarios["metadata_negative_cache"]
    shared = scenarios["metadata_shared_redis"]

    if cold["upstream_calls"] != 1:
        raise RuntimeError("cold same-key burst must collapse to exactly one upstream request")
    if cold["coalesced_followers"] < 1:
        raise RuntimeError("cold same-key burst did not exercise request coalescing")
    if warm["additional_upstream_calls"] != 0:
        raise RuntimeError("warm metadata cache unexpectedly contacted the upstream provider")
    if warm["p95_ms"] >= report["provider_delay_ms"] * 0.5:
        raise RuntimeError("warm metadata cache p95 did not materially beat provider latency")
    if negative["total_upstream_calls"] != 1:
        raise RuntimeError("safe not-found workload must contact upstream exactly once")
    if negative["additional_upstream_calls"] != 0:
        raise RuntimeError("negative cache did not suppress repeated safe not-found requests")
    if negative["negative_cache_hits"] < report["consumers"]:
        raise RuntimeError("negative-cache burst did not serve every repeated request from cache")
    if shared.get("skipped"):
        raise RuntimeError("Redis-backed shared coalescing benchmark was skipped")
    if shared["upstream_calls"] != 1:
        raise RuntimeError("Redis-backed shared-worker burst must collapse to one upstream request")


def _markdown(report: dict) -> str:
    scenarios = {item["name"]: item for item in report["scenarios"]}
    cold = scenarios["metadata_cold_same_key"]
    warm = scenarios["metadata_warm_cache"]
    negative = scenarios["metadata_negative_cache"]
    shared = scenarios["metadata_shared_redis"]
    lines = [
        "# LoreX PR7 Metadata Cache and Request Coalescing Benchmark",
        "",
        f"- Product: `{report['product_version']}`",
        f"- Python: `{report['environment']['python']}`",
        f"- Consumers per burst: `{report['consumers']}`",
        f"- Synthetic provider latency: `{report['provider_delay_ms']:.1f} ms`",
        "",
        "## Cold same-key burst",
        "",
        f"- p50/p95: `{cold['p50_ms']:.3f}` / `{cold['p95_ms']:.3f}` ms",
        f"- Upstream requests: `{cold['upstream_calls']}`",
        f"- Coalesced followers: `{cold['coalesced_followers']}`",
        "",
        "## Warm cache burst",
        "",
        f"- p50/p95: `{warm['p50_ms']:.3f}` / `{warm['p95_ms']:.3f}` ms",
        f"- Additional upstream requests: `{warm['additional_upstream_calls']}`",
        "",
        "## Negative cache burst",
        "",
        f"- p50/p95: `{negative['p50_ms']:.3f}` / `{negative['p95_ms']:.3f}` ms",
        f"- Total upstream requests including prime: `{negative['total_upstream_calls']}`",
        f"- Additional upstream requests during repeat burst: `{negative['additional_upstream_calls']}`",
        f"- Negative cache hits: `{negative['negative_cache_hits']}`",
        "",
        "## Shared Redis coalescing",
        "",
    ]
    if shared.get("skipped"):
        lines.extend([f"- Skipped: `{shared.get('reason', 'Redis unavailable')}`", ""])
    else:
        lines.extend(
            [
                f"- p50/p95: `{shared['p50_ms']:.3f}` / `{shared['p95_ms']:.3f}` ms",
                f"- Upstream requests: `{shared['upstream_calls']}`",
                f"- Coalesced followers: `{shared['coalesced_followers']}`",
                "",
            ]
        )
    lines.extend(
        [
            "This benchmark uses a deterministic synthetic provider delay and never calls Open Library or Google Books. It validates request reduction, TTL-cache behavior, and same-key coordination rather than public-provider network speed.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report: dict, output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "pr7-metadata.json"
    markdown_path = output / "pr7-metadata.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmark-results")
    parser.add_argument("--consumers", type=int, default=100)
    parser.add_argument("--provider-delay", type=float, default=0.05)
    args = parser.parse_args()

    report = run_metadata_benchmarks(
        consumers=args.consumers,
        provider_delay=args.provider_delay,
        redis_url=os.environ.get("LOREX_REDIS_URL"),
    )
    enforce_gates(report)
    _, markdown_path = write_report(report, args.output)
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
