# LoreX Whole-App Optimization Design

## Status

Approved and locked on 2026-09-01.

## Goal

Make LoreX fast, predictable, and resource-efficient from version `0.0.1` onward by requiring measurement-backed optimization across indexing, persistence/search, downloader/import processing, metadata access, and the web UI.

LoreX must not claim an optimization is complete unless the intended performance metric improves on a fresh benchmark without introducing unacceptable regressions elsewhere.

## Core Principles

1. **Measure before tuning.** Every optimization PR starts from a reproducible baseline.
2. **Bound memory.** Backfill/indexing memory usage must depend on configured batch sizes, not total history size.
3. **Avoid linear scans at scale.** Search, wanted matching, and dashboard reads must use indexed database access paths.
4. **Stream large payloads.** NNTP articles, archive/media processing, and file movement must avoid whole-file RAM buffering.
5. **Throttle persistence.** High-frequency progress events are coalesced so PostgreSQL and Redis are not dominated by status writes.
6. **Keep work isolated.** Indexing, downloading, repair/extraction, importing, metadata, and UI reads must have bounded concurrency so one workload cannot starve the others.
7. **Generate expensive artifacts lazily.** Full NZB documents are generated and cached on demand rather than eagerly for every accepted release.
8. **Preserve correctness.** Performance changes use red-green tests and must not weaken deduplication, recovery, verification, sanitization, provider fallback, or metadata confidence rules.
9. **Serial PR order is mandatory.** Later PRs depend on the measurements and interfaces established by earlier PRs.
10. **Version remains `0.0.1` during this optimization program unless explicitly changed.**

## Performance Budgets

These are initial engineering gates, not product claims. They may only be changed by updating this design with benchmark evidence.

- Search API p95: **< 150 ms** at 1,000,000 indexed releases.
- Normal read API p95: **< 100 ms** under representative single-user load.
- Dashboard aggregate API p95: **< 250 ms**.
- Header processing: **>= 25,000 headers/sec** on the benchmark reference environment after the relevant indexing work lands.
- Backfill/index memory: bounded by configured batch/concurrency limits rather than total backfill size.
- Search implementation: no full in-memory scan of the release catalog for normal queries.
- Downloader memory: article payloads streamed to disk; throughput should be limited by provider/network/disk before Python memory copying.
- Idle CPU: near-zero outside scheduled/background work.
- Metadata coalescing: at most one active upstream request per cache key; concurrent consumers share the result.
- UI: large logical result sets use server pagination/virtualization so browser work does not grow linearly with total catalog size.

## Target Architecture

```text
NNTP
  -> bounded header batches
  -> normalization / multipart grouping / classification
  -> PostgreSQL bulk persistence
  -> lightweight searchable release rows
  -> lazy NZB generation/cache
  -> Redis-backed work queues
  -> streaming multi-provider downloader
  -> bounded PAR2 / extraction workers
  -> metadata cache + request coalescing
  -> bounded importer/media processing
  -> managed M4B-first library
  -> lightweight paginated API projections
  -> responsive React UI
```

PostgreSQL remains authoritative persistent state. Redis is used only for short-lived cache, queues, locks, coalescing, and progress coordination; durable truth must not depend on Redis survival.

## Required Serial PRs

### PR 1 — Benchmark Harness and Performance Baseline

Create reproducible synthetic workloads for at least 10K, 100K, and 1M-scale logical data where practical. Capture:

- headers/sec
- candidate grouping/classification throughput
- peak memory/RSS
- release search p50/p95
- dashboard/read API p50/p95
- queue operations/sec
- downloader fixture throughput
- importer fixture processing time
- frontend production build size and representative render/load measurements

CI must publish benchmark results as artifacts or clearly readable job output. Performance benchmarks are not permitted to make normal CI flaky; correctness tests remain hard gates.

No optimization is considered proven until PR 1 provides a baseline for its metric.

### PR 2 — Streaming Indexer Pipeline

Replace whole-workload list assumptions with bounded batches and explicit checkpoints.

Requirements:

- normalize subjects once per header
- bounded batch memory
- minimize sorting; only sort where correctness requires ordering
- release processed batch memory promptly
- checkpoint live/backfill positions transactionally
- batch database writes
- deduplicate live/backfill overlap
- preserve progressive obfuscation inspection hooks
- measure headers/sec and peak memory against PR 1

### PR 3 — PostgreSQL Persistence and Query Indexes

Replace in-memory repositories as authoritative storage.

Required indexed access paths include:

- normalized release title
- normalized author
- narrator
- ISBN-10 / ISBN-13
- ASIN
- series and series position
- posted date
- message ID
- release fingerprint/dedupe key
- wanted matching fields
- download/import status fields used by UI filters

Use migrations. Bulk ingestion must avoid per-row transaction overhead. Redis must not become authoritative state.

### PR 4 — Fast Search and Lightweight Read APIs

Remove full-catalog scans and oversized response objects.

Requirements:

- server-side pagination
- explicit sort/filter parameters
- lightweight list projections separate from detail objects
- PostgreSQL full-text and/or trigram indexes where benchmark evidence supports them
- no `list(all_rows)` pattern on normal search/list endpoints
- dashboard queries avoid N+1 behavior
- search p95 target evaluated at 1M releases

### PR 5 — Queue and Downloader Efficiency

Move durable work coordination to PostgreSQL with Redis-assisted queues/locks where appropriate.

Requirements:

- no O(n) queue head removal pattern such as list `pop(0)`
- bounded article/download concurrency
- configurable provider connection pools
- TLS providers with priority/fill-server behavior
- automatic article-level fallback
- stream payloads directly to disk
- coalesce progress persistence
- resumable article status
- provider health metrics retained
- downloader CPU/RAM overhead measured separately from provider/network throughput

### PR 6 — Importer and Media Pipeline Efficiency

Optimize verification, PAR2, extraction, FFmpeg/FFprobe, tagging, and final moves without weakening safety.

Requirements:

- avoid unnecessary file copies
- preserve/remux valid M4B without re-encoding
- bounded FFmpeg/PAR2/extraction concurrency
- CPU-heavy processing cannot starve API/indexer/downloader work
- source cleanup only after verified final-file success
- archive traversal and extraction-size safeguards remain enforced
- oldest completed items processed first
- importer benchmark compares wall time, CPU, and temporary disk usage

### PR 7 — Metadata Cache and Request Coalescing

Add shared metadata efficiency for Open Library, Google Books, and future providers.

Requirements:

- cache by stable normalized lookup keys
- TTLs appropriate to metadata type
- negative caching for safe not-found responses
- one active upstream request per key
- retry/backoff without request storms
- artwork fetch/processing asynchronous from critical read paths
- extracted local metadata remains available when external providers fail
- credentials/secrets never enter cache keys or logs

### PR 8 — UI and API Responsiveness

Optimize the approved light-mode LoreX UI after backend access patterns are stable.

Requirements:

- route/code splitting where measurable
- debounced search
- server pagination/filtering
- virtualized rendering for very large visible collections when needed
- cache stable query results
- avoid redundant polling
- coalesce progress updates
- dashboard loads from lightweight aggregate endpoints
- no large catalog payloads sent merely to render counts or first-page lists
- responsive behavior preserved for desktop, tablet, and mobile

## Benchmark Data Rules

Synthetic data must be deterministic from a fixed seed so before/after results are comparable. Large benchmark fixtures should be generated, not committed as huge repository blobs.

Benchmarks must distinguish:

- CPU-bound work
- database-bound work
- network/provider-bound work
- disk-bound work
- external metadata-provider latency

A change must not be credited with improving LoreX if the result comes only from reducing the amount of correctness work performed.

## Observability

Expose enough internal timing/counters to diagnose regressions without enabling verbose production logging by default.

Minimum useful metrics include:

- headers received/processed/rejected/indexed
- grouping/classification durations
- database batch duration and rows/sec
- search latency and result count
- queue depth and age
- article throughput and provider fallback rate
- verify/repair/extract duration
- FFmpeg processing duration
- metadata cache hit/miss/coalesced-request counts
- API request latency by route family

## Failure and Recovery Constraints

Optimization must preserve these existing product rules:

- indexer checkpoints allow safe restart
- downloader resumes persisted article state
- provider fallback remains automatic
- importer stages are transactional/recoverable
- final source cleanup never occurs before output verification
- low-confidence metadata never silently becomes a match
- duplicate detection must distinguish alternate editions/narrations from true duplicates
- path sanitization and archive traversal protections remain mandatory

## Review and Merge Policy

The eight optimization PRs are serial and merge in the order listed above. Every PR must include:

1. failing/red tests where behavior changes
2. passing correctness tests
3. the relevant benchmark before and after
4. a short regression review for CPU, memory, disk, database, and API impact
5. fresh CI evidence on the exact head being merged

A PR that merely changes implementation without measurable benefit to its stated performance goal is not considered an optimization PR and should not be merged under this program.

## Out of Scope

This program does not add multi-user support, native mobile applications, recommendation systems, general movie/TV/music indexing, or a full streaming player. Those features may be designed later and must inherit the performance budgets and bounded-resource principles established here.
