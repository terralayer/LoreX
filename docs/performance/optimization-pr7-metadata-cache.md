# LoreX Optimization PR 7 — Metadata Cache and Request Coalescing

## Status

Optimization PR 7 adds bounded metadata caching and same-key request coalescing for LoreX `0.1.1 alpha`. The measurements below were produced by GitHub Actions run `33818795331` on commit `849e225036031e74cf1e8923a905414e1e759fa1` after the PR-specific benchmark was wired into CI.

The uploaded `lorex-benchmark-baseline` artifact contains the baseline, PR 6 importer report, PR 7 metadata JSON/Markdown, and runner logs. Artifact ID: `9917613256`; uploaded artifact SHA-256: `40760f58f25fef0cb1169767e6a38940d18a65ddf9912530137a9d277593c814`.

These are deterministic synthetic-provider measurements. They prove cache/coalescing behavior and request reduction; they are not claims about public Open Library or Google Books network latency.

## PR 7 Evidence

The benchmark uses 100 concurrent consumers and a deterministic 50 ms fake metadata provider.

| Scenario | p50 | p95 | Upstream requests | Result |
| --- | ---: | ---: | ---: | --- |
| Cold same-key burst | 0.002 ms | 50.021 ms | 1 | 100 callers collapsed to one provider request |
| Warm cache burst | 0.002 ms | 0.004 ms | +0 | Served entirely from cache |
| Negative-cache repeat burst | 0.004 ms | 0.009 ms | +0 | 100 negative cache hits after one safe not-found prime |
| Shared Redis coalescing | 2.849 ms | 72.581 ms | 1 | Two resolver instances collapsed the burst to one provider request |

Cold local coalescing recorded 31 followers because the thread pool runs at most 32 workers at once; later callers enter after the leader has populated the cache. Shared Redis coalescing likewise recorded 31 active followers while still proving exactly one provider request across two resolver instances.

Warm-cache p95 is approximately 0.008% of the synthetic 50 ms provider delay and easily satisfies the PR 7 gate requiring warm p95 to remain below half of provider latency.

## Cache and Failure Semantics

- Positive metadata TTL defaults to 7 days.
- Safe not-found negative-cache TTL defaults to 15 minutes.
- Transient provider failures are never negative-cached.
- Cache keys use normalized ISBN/ASIN/title-author identities.
- Redis storage and lease keys hash lookup identities before storing them.
- Redis is an accelerator only: resolver failure falls back to an in-memory cache plus process-local same-key coordination.
- Distributed leases use token-checked compare-and-delete release semantics.
- Followers wait for a bounded period and can recover leadership after a lease expires or Redis becomes unavailable.
- Provider retries are bounded to three attempts and only cover transport failures, HTTP 429, and HTTP 5xx responses.
- `Retry-After` is honored but capped.
- Google Books API credentials are not included in provider exception messages.
- Local metadata remains usable when external metadata providers fail.
- Artwork enrichment runs through a bounded two-worker scheduler by default and duplicate artwork jobs coalesce by metadata key.

## Regression Review

The same CI run retained the existing whole-app gates:

- Streaming indexer at 100K headers: `36,926.8 headers/sec`, still above the locked 25K headers/sec gate.
- PostgreSQL one-million-release search: `63.923 ms p95`, still below the locked 150 ms p95 search target.
- PR 6 valid-M4B preserve path: `66.337 ms p95`, with zero payload-copy bytes and 50% lower temporary disk peak than the legacy copy fixture.
- Frontend production build remained `160,621` raw bytes / `51,707` deterministic gzip bytes.

Hosted runner timing varies between runs, so unrelated scenario movement is treated as variance unless a PR-specific workload or repeated evidence indicates otherwise.

## CI Contract

PR 7 is not considered verified unless CI runs all of the following on the same head:

1. PostgreSQL + Redis-backed backend test suite.
2. Frontend production build.
3. Whole-app deterministic baseline/regression suite.
4. PR 6 importer regression benchmark.
5. `python -m benchmarks.run_pr7`, including its hard metadata gates.
6. Benchmark summary publication and artifact upload.

PR 8 UI/API responsiveness work remains intentionally outside this PR.
