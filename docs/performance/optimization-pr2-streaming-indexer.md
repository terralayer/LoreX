# LoreX Optimization PR 2 — Streaming Indexer Results

## Status

Optimization PR 2 replaces the original whole-list indexing path with a bounded streaming multipart pipeline, explicit batch persistence/checkpoints, overlap deduplication, and lazy NZB generation.

The reference results below came from GitHub Actions run `33592542712` on branch commit `a5f67b864287fbbab2f7cecf221c59f36232c04d`. The benchmark artifact `lorex-benchmark-baseline` has SHA-256 digest `e921de6e9c50c3352258b2de9d77910d772f68e5d239b6413060e4279ae79936`.

The comparison baseline is `docs/performance/baseline-0.1.1-alpha.md`, measured in PR 1. Both measurements use the same deterministic benchmark generators and logical scales. Hosted GitHub runners are not performance-isolated, so small changes in unrelated scenarios are treated as runner variance unless repeated evidence points to a code effect.

## What Changed

- Header ingestion now accepts iterables of bounded `IndexBatch` values rather than requiring the entire backfill as one list.
- Multipart grouping normalizes the subject/part suffix once in the streaming hot path.
- Pending multipart state is capped by `max_pending_groups`; unresolved eviction is routed to the inspection hook rather than growing without bound.
- Explicit part ordering is performed only when a multipart candidate completes.
- Accepted releases are committed through `ReleaseRepository.commit_index_batch()` with their article references and optional checkpoint.
- Checkpoints are monotonic and prevalidated before mutation; a regressing checkpoint rejects the batch before release/checkpoint state changes.
- Replayed release IDs are treated as live/backfill overlap duplicates rather than creating duplicate release records.
- Accepted releases no longer serialize full NZB XML while indexing. Article references are retained and the NZB is generated/cached on first request.
- `GET /api/releases/{release_id}/nzb` exposes the lazily generated NZB.
- The legacy `index_headers()` entry point remains as a compatibility wrapper.

## Streaming Benchmark Configuration

The `index_headers` benchmark keeps the PR-1 scenario name and logical workload but now exercises the real streaming service with:

- input header batch: `2,048`
- accepted-release write batch: `512`
- maximum pending multipart groups: `4,096`

These settings bound active grouping/write state independently of total backfill history.

## Primary Result

| Metric | PR 1 baseline | PR 2 | Change |
| --- | ---: | ---: | ---: |
| `index_headers` throughput @ 100K | 9,213.4 headers/sec | **38,044.6 headers/sec** | **+312.9% / 4.13×** |
| `index_headers` p95 @ 100K | 10,853.757 ms | **2,628.497 ms** | **-75.8%** |
| `index_headers` peak Python @ 100K | 43.39 MB | **21.31 MB** | **-50.9%** |
| process RSS high-water after 100K index stage | 160.42 MB | **131.26 MB** | **-18.2%** |
| `group_and_classify` throughput @ 100K | 61,748.7 headers/sec | **66,453.6 headers/sec** | **+7.6%** |
| `group_and_classify` peak Python @ 100K | 16.50 MB | **12.80 MB** | **-22.4%** |

The locked PR-2 target was at least `25,000 headers/sec` at the 100K reference scale. The exact-head result is `38,044.6 headers/sec`, so the throughput target is met with approximately 52% headroom above the gate.

## Full Reference Run

| Scenario | Scale | p95 ms | Throughput/sec | Peak Python MB |
| --- | ---: | ---: | ---: | ---: |
| `index_headers` | 10,000 headers | 256.830 | 38,941.6 | 2.20 |
| `index_headers` | 100,000 headers | 2,628.497 | 38,044.6 | 21.31 |
| `group_and_classify` | 10,000 headers | 145.949 | 68,563.2 | 1.29 |
| `group_and_classify` | 100,000 headers | 1,504.810 | 66,453.6 | 12.80 |
| `release_search` | 10,000 releases | 26.672 | 377,925.1 | 0.08 |
| `release_search` | 100,000 releases | 271.405 | 371,820.4 | 0.76 |
| `release_search` | 1,000,000 releases | 2,631.523 | 381,357.0 | 7.63 |
| `release_search_api` | 10,000 releases | 29.132 | 349,654.8 | 0.14 |
| `release_search_api` | 100,000 releases | 259.600 | 392,494.2 | 0.81 |
| `queue_roundtrip` | 10,000 jobs | 103.307 | 194,103.8 | 1.67 |
| `mock_downloader` | 10,000 downloads | 57.541 | 174,296.2 | 0.00 |
| `library_importer` | 10,000 imports | 142.133 | 71,118.4 | 2.89 |

Frontend production size remained exactly `160,621` raw bytes / `51,707` deterministic gzip bytes.

## Regression Review

### Indexing CPU/time

This is the intentional change. Full 100K indexing improves from `9.2K` to `38.0K headers/sec`. The gain comes from removing eager NZB XML generation, eliminating whole-workload grouping/sorting, reducing parsing/allocation overhead in the hot loop, and committing bounded accepted-release batches.

### Indexing memory

The benchmark's scenario-specific Python allocation peak falls by `50.9%` at 100K. The process RSS high-water after the indexing/grouping stage is also lower (`131.26 MB` vs `160.42 MB`). RSS remains a process-wide cumulative high-water metric and is not a per-scenario allocation delta.

The benchmark generator still constructs the 100K synthetic header input before timing, so this measurement does not prove the memory footprint of a real network source that yields headers incrementally. The implementation itself no longer requires total-history materialization and caps pending multipart/write state; realistic NNTP-source memory will be measured once the real source worker exists.

### Grouping/classification

An intermediate implementation regressed the standalone grouping scenario. That version was not accepted. Hot-loop object/list dispatch was removed and the final exact-head run reaches `66.45K headers/sec`, `7.6%` above the PR-1 baseline, with `22.4%` lower Python peak allocation.

### Search/API

Search code was not intentionally optimized in this PR. The final run is faster than PR 1 (`2.632 s` p95 at 1M releases versus `3.015 s`, and `259.6 ms` p95 for the 100K representative API versus `290.8 ms`), but those improvements are not attributed to PR 2 because the search implementation is unchanged and hosted-runner variance is material. Indexed persistent search remains PR 3/4 work.

### Queue/downloader/importer

The final run differs only a few percent from PR 1 in these unrelated fixture scenarios. No production queue, downloader, or importer optimization claim is made here. Their dedicated work remains in later serial PRs.

### Frontend

No frontend production code changed. Raw and deterministic gzip build sizes are byte-for-byte unchanged from PR 1.

## Correctness and Reliability Properties

- A multipart release may span input batches and still completes correctly.
- Duplicate part numbers do not create duplicate article entries in a completed candidate.
- Pending multipart groups are bounded; incomplete eviction is surfaced to the inspection hook.
- Batch checkpoint regression is rejected before mutation.
- Live/backfill replay of an existing release ID is counted as a duplicate rather than inserted again.
- Persisted article references are sufficient to generate a valid NZB after indexing.
- NZB XML remains empty on the indexed release record until requested; the first request generates/caches it and later requests reuse the cache.
- Existing search/grab/download/import vertical-slice behavior remains covered by the backend suite.

## Checkpoint Boundary

PR 2 deliberately does **not** invent article-number checkpoints. `IndexBatch.checkpoint` is an explicit source-provided safe point. The in-memory implementation guarantees monotonic batch commit semantics for the checkpoint it is given, but pending multipart state is not itself durable across process failure yet.

PR 3 will map the batch-commit boundary to PostgreSQL transactions and durable index state. A real NNTP source must only emit a checkpoint at a position it can safely replay from after restart; overlap replay is expected and deduplicated.

## Scope Boundary

PR 2 does not introduce PostgreSQL, database indexes, trigram/full-text search, Redis queues, or downloader/media-processing concurrency. Those remain in the locked serial PR order.

## Verification

Before this result was recorded:

- all backend correctness tests passed on commit `a5f67b864287fbbab2f7cecf221c59f36232c04d`
- frontend production build passed
- full CI benchmark profile passed
- benchmark summary publication passed
- benchmark artifact upload passed

A fresh final-head CI run is still required after this documentation commit before merge.
