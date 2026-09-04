# LoreX Optimization PR 8: UI and API Responsiveness

## Status

This document records the performance evidence for the eighth and final stage of the locked LoreX `0.1.1 alpha` whole-app optimization program.

The measured implementation head was `3a088fce1671d8422dabf74af4bd13e30616de07`. GitHub Actions run `33835816201` completed successfully and uploaded the `lorex-benchmark-baseline` artifact with SHA-256 digest `12b46330b268e010c1db4eb62a4c5ca4369c2531d771cf6e9aca17f2607e561a`.

These are engineering measurements from the deterministic CI harness, not universal deployment guarantees.

## PR 8 Scope

PR 8 adds the UI/read-path work defined by the locked optimization design:

- lightweight dashboard aggregate reads
- bounded server-side library pagination/filtering
- supporting PostgreSQL read indexes
- React route/code splitting
- debounced search
- bounded/windowed large-list rendering
- stable query caching and in-flight request coalescing
- visibility-aware refresh behavior

## Measured Gates

The PR 8 benchmark seeded PostgreSQL with 100,000 releases and 100,000 library books, plus 1,000 download jobs, and collected 20 timed samples.

| Gate | Measured result | Locked target | Result |
| --- | ---: | ---: | --- |
| Lightweight dashboard aggregate p95 | `19.581 ms` | `<250 ms` | PASS |
| Paged library read p95 | `15.916 ms` | `<100 ms` | PASS |
| Library page size | `50 rows` | bounded | PASS |
| Library page response payload | `7,704 bytes` | bounded | PASS |
| Dashboard response payload | `94 bytes` | lightweight | PASS |
| Dashboard peak Python allocation | `0.091 MiB` | bounded | PASS |
| Library read peak Python allocation | `0.248 MiB` | bounded | PASS |

The library read measurement intentionally used an offset of `50,000` to exercise a deep page rather than only the first page.

## Frontend Startup Evidence

The production Vite build produced six JavaScript files: one startup entry and five lazy chunks.

- Startup entry: `148,610` raw bytes
- Startup deterministic gzip: `48,008` bytes
- PR 1 primary JavaScript baseline: `151,610` raw / `48,670` gzip bytes
- Lazy JavaScript chunks: `5`

The initial JavaScript entry is therefore smaller than the PR 1 baseline while route-specific code is split into lazy chunks.

The complete PR 8 production build contained nine files totaling `175,963` raw bytes and `57,917` deterministic gzip bytes. Total application bytes are not the startup gate: PR 8 intentionally trades a modest increase in total routed application code for a smaller initial entry and deferred route loading.

## Whole-App Regression Context

The same CI run retained earlier optimization gates:

- 100,000-header streaming indexing: `44,452.9 headers/sec`, above the locked `25,000 headers/sec` target.
- PostgreSQL 1,000,000-release search: `66.519 ms p95`, below the locked `<150 ms` target.
- PR 6 valid-M4B preserve workload remained copy-free for payload bytes and retained the 50% temporary-disk reduction.
- PR 7 metadata-cache/coalescing benchmarks retained one upstream request per same-key burst and zero additional requests for warm/negative cache bursts.

Hosted-runner timing varies between runs; correctness gates and threshold margins, rather than tiny timing deltas, are authoritative.

## Verification

On run `33835816201`:

- backend tests passed with PostgreSQL/Redis services and migrations applied
- frontend TypeScript/Vite production build passed
- whole-app benchmark passed
- PR 6 benchmark passed
- PR 7 benchmark passed
- PR 8 benchmark passed
- benchmark summary publication passed
- benchmark artifact upload passed

A fresh exact-head CI run is required after this documentation-only commit before PR 8 is merged.
