# Optimization PR 6 — Importer and Media Pipeline Efficiency

## Exact-head benchmark evidence

Measured on GitHub Actions CI for commit `929f3cb88289af7f7e6da68a2d8789bc305940fe` using Python 3.12.14 on Linux x86_64. The exact-head run completed backend tests, frontend build, Alembic migrations through `0004_import_pipeline_efficiency`, the locked whole-app benchmark, the PR6 importer benchmark, summary publication, and artifact upload successfully.

### Valid M4B preserve workload

Deterministic workload: 64 valid M4B files at 64 KiB each on one filesystem. External codec latency is intentionally excluded because valid M4B must not be re-encoded. The comparison reproduces a legacy copy-then-delete import versus PR6 verified atomic promotion.

| Metric | Legacy copy path | PR6 preserve path | Change |
| --- | ---: | ---: | ---: |
| p50 wall time | 164.311 ms | 70.339 ms | 57.2% lower |
| p95 wall time | 164.378 ms | 71.255 ms | 56.7% lower (~2.31x faster) |
| CPU sample | 55.763 ms | 24.385 ms | 56.3% lower |
| Peak temporary disk | 8,388,608 bytes | 4,194,304 bytes | 50.0% lower |
| Payload bytes copied | 4,194,304 bytes | 0 bytes | 100% reduction |
| Media action | n/a | 64 preserve / 0 remux / 0 transcode | no unnecessary re-encode |

The same-filesystem optimized path verifies the source, preserves valid M4B, atomically promotes it with `os.replace`, verifies the destination, persists the library record, marks the import complete, and only then performs source/staging cleanup. Cross-filesystem promotion retains the streaming copy + fsync + verification fallback because a payload copy is unavoidable there.

### Durable PostgreSQL import queue

A 250-job deterministic fixture was seeded outside the measured interval. The measured path used durable PostgreSQL oldest-first claims with `FOR UPDATE SKIP LOCKED` and terminal state transitions.

- Jobs: 250
- p50/p95: 1,788.923 ms / 1,788.923 ms
- Approximate throughput: 139.75 jobs/sec
- Oldest-first ordering preserved: true

This queue result is a durability/ordering measurement, not a claim that database transactions should beat an in-memory queue. PostgreSQL remains authoritative so restart and concurrent-worker correctness are preserved.

## Correctness and resource regression review

### CPU and concurrency

PAR2 repair, extraction, and FFmpeg/FFprobe work use separate bounded semaphores. Tests verify positive limits and separate gates so CPU-heavy media work cannot grow unbounded or consume downloader concurrency. Valid M4B stays on the preserve path; compatible AAC/ALAC in another container uses FFmpeg stream-copy remux, and transcoding is reserved for unsupported/invalid media.

### Memory

The pipeline does not read whole media payloads into Python memory. Same-filesystem promotion is a rename. Cross-filesystem fallback streams copies in 1 MiB chunks. Archive validation works from member metadata and enforces file-count and expanded-size budgets before extraction.

### Disk and cleanup safety

Archive members are validated before 7z execution. Absolute paths, parent traversal, invalid sizes, file-count overflow, and expanded-size overflow are rejected. Final media verification occurs before promotion. If library persistence fails after a move, the file is restored to its pre-promotion location. Source/staging cleanup is invoked only after the library row is persisted and the import is durably marked completed. A restart at the moving stage accepts an already-present verified destination instead of attempting a destructive second move.

### Recovery

Import jobs persist source/staging/final paths, stage, claims, timestamps, errors, and metrics in PostgreSQL. Stale worker claims return to queued state without discarding stage or staging-path state. Resume tests prove post-remux work can continue from tagging without rerunning remux and post-move work can finish from an already-verified library destination.

## Scope

This evidence covers serial Optimization PR 6 only: import coordination, verification/repair/extraction safety, media processing policy, verified moves, cleanup ordering, recovery, and importer benchmarks. Metadata cache/request coalescing remains PR 7; UI/API responsiveness remains PR 8.
