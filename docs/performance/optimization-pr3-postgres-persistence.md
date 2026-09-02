# Optimization PR 3 — PostgreSQL Persistence and Query Indexes

## Scope

Optimization PR 3 replaces LoreX's in-memory repositories as authoritative application state when `LOREX_DATABASE_URL` is configured. It adds PostgreSQL 16 persistence, Alembic migrations, durable release/article/checkpoint/library/download-job state, and the indexed access paths required by the locked whole-app optimization design.

This PR intentionally does **not** redesign full-text search, pagination, lightweight list projections, or dashboard/read APIs. Those remain Optimization PR 4.

## Correctness and durability evidence

The CI backend job runs against a real PostgreSQL 16 service after `alembic upgrade head` and verifies:

- release persistence and reconstruction
- durable article references
- monotonic transactional indexer checkpoints
- rollback when a checkpoint regresses
- release replay/deduplication
- durable lazy-NZB cache
- durable library records
- durable FIFO download jobs
- PostgreSQL-backed application container selection
- large bulk ingestion across PostgreSQL's bind-parameter ceiling

A discovered production-scale failure was reproduced and fixed during this PR. A 10,000-release `INSERT ... ON CONFLICT` expanded to roughly 130,000 bind parameters, exceeding psycopg/PostgreSQL's 65,535 parameter protocol limit. Release and article inserts are now split under a conservative 60,000-bind budget while remaining inside the same transaction. A 6,000-release regression test crosses the former failure boundary and passes.

## Indexed access paths

The schema/migration provides indexed or unique access paths for:

- normalized release title
- normalized author
- narrator
- ISBN-10 / ISBN-13
- ASIN
- series + series position
- posted date
- message ID
- release fingerprint/deduplication key
- wanted matching key
- download status
- import status
- queued download status/order

PostgreSQL is authoritative state. Redis is not used as authoritative persistence in this PR.

## Fresh measured results

Source: GitHub Actions CI on Linux/x86_64, Python 3.12.14, PostgreSQL 16, exact implementation head `3b48af0b31a76f381140122fbc7fcf4d18c9af44`.

| Scenario | Scale | p50 | p95 | Throughput | Peak Python allocation |
| --- | ---: | ---: | ---: | ---: | ---: |
| PostgreSQL bulk release persistence | 10,000 releases | 19,522.24 ms | 19,522.24 ms | 512.2 releases/sec | 65.64 MB |
| PostgreSQL normalized-title indexed lookup | 10,000-row table | 1.759 ms | 1.870 ms | 567.4 lookups/sec | 0.02 MB |
| Streaming header indexing regression check | 100,000 headers | 2,887.91 ms | 2,887.91 ms | 34,627.1 headers/sec | 21.31 MB |

The PostgreSQL bulk scenario measures a single transaction and excludes synthetic fixture generation. It is the first durable-database ingestion reference, not a claim that storage throughput is final. Production streaming currently persists much smaller bounded write batches, and later tuning must compare against this reference rather than silently reducing durability work.

The normalized-title lookup demonstrates that the new B-tree access path is fast at the current 10,000-row PostgreSQL benchmark scale. It does **not** satisfy the locked 1M-release search target by itself; Optimization PR 4 owns full search/read API redesign and the 1M p95 gate.

## Regression observations

The PR-2 streaming indexer remains comfortably above the locked 25,000 headers/sec target in this hosted-runner measurement at 34,627.1 headers/sec. Hosted runner variance is expected, so this should be interpreted as a regression guard rather than a precise comparison to a single earlier run.

The legacy in-memory tail-search benchmark remains approximately linear and is still about 2.9 seconds p95 at one million releases. That is an intentionally unresolved PR-4 target, not evidence against the PostgreSQL indexed point lookup added here.

## CI diagnostics

Benchmark stdout/stderr is now captured in `benchmark-results/runner.log`, and the benchmark artifact is uploaded even on a benchmark failure when diagnostic files exist. This change was necessary to capture the exact psycopg bind-limit traceback and should remain because it materially improves future performance-regression diagnosis.

## Conclusion

PR 3 establishes durable PostgreSQL authority and the query indexes needed by subsequent optimization work, while preserving transactional checkpoint/deduplication behavior. Its database benchmark now succeeds at 10,000 releases after fixing the parameter-limit failure. Search/list API optimization is deliberately deferred to serial Optimization PR 4.