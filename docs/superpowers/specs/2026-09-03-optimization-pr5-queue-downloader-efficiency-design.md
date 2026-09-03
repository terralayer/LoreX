# Optimization PR 5: Queue and Downloader Efficiency

## Status

Approved in chat on 2026-09-03. Written spec awaiting final review before implementation.

## Goal

Make LoreX download work durable, resumable, bounded, and resource-efficient while preserving provider fallback and recovery guarantees. PostgreSQL remains authoritative for durable queue/job/article state. Redis may assist with short-lived queue acceleration, locks, and coordination, but LoreX must recover correctly if Redis is unavailable or loses state.

PR 5 remains on LoreX `0.1.1 alpha` and must stay isolated from PR 6 importer/media-pipeline work and later metadata/UI optimization work.

## Scope

PR 5 adds:

- durable PostgreSQL download-job lifecycle instead of destructive dequeue semantics;
- durable per-article download state for restart/resume;
- efficient in-memory compatibility queue behavior without O(n) head removal;
- bounded download and article concurrency;
- configurable TLS NNTP providers with priority, connection limits, and fill-server behavior;
- automatic article-level provider fallback;
- streamed article payload writes directly to disk;
- coalesced progress persistence;
- retained provider health metrics;
- deterministic queue/downloader benchmark coverage that separates application CPU/RAM overhead from simulated provider/network delay.

Explicitly out of scope: PAR2 repair, archive extraction, FFmpeg/FFprobe, media tagging/remuxing, importer ordering/cleanup changes, metadata caching, and frontend optimization.

## Durable Queue Model

`download_jobs` remains the authoritative job table. Jobs are not deleted when claimed. A worker claims the oldest eligible queued job transactionally using PostgreSQL row locking with `FOR UPDATE SKIP LOCKED`, changes it to `downloading`, and records claim/recovery metadata. Terminal transitions are `completed` and `failed`; interrupted or stale in-progress jobs are recoverable without creating duplicate durable work.

The in-memory development/test repository uses `collections.deque` and `popleft()` so compatibility behavior does not retain the existing O(n) list-head removal pattern.

Durable queue ordering remains oldest-first by `created_order`. Multiple workers must not claim the same job concurrently.

## Article State and Resume

Each release article participating in a download has durable download state keyed by the release/job and article identity. At minimum the stored state distinguishes pending, in-progress, completed, and failed articles and retains enough data to resume without re-downloading already completed articles.

A restarted worker reconstructs remaining work from PostgreSQL. Completed article records are skipped. In-progress article records left by an interrupted worker become eligible for retry through an explicit recovery rule rather than being silently treated as complete.

Article state may include provider-attempt metadata required for diagnostics, but provider health history itself is modeled separately so a single article row does not become an unbounded event log.

## Provider Configuration and Connection Pools

Providers are explicit immutable configuration objects with:

- provider name/identifier;
- hostname and TLS port;
- TLS required for production NNTP connections;
- priority;
- fill-server flag;
- maximum connection count;
- enabled state.

Primary providers are attempted by priority. Fill servers participate when higher-priority providers cannot supply an article. Connection pools enforce per-provider limits, and the downloader enforces a separate global article/download concurrency ceiling so provider configuration cannot create unbounded tasks or memory use.

PR 5 introduces provider configuration injection through application configuration/environment values. Credentials are runtime secrets, are never persisted in PostgreSQL, and must not appear in logs, metrics labels, benchmark fixtures, cache keys, or diagnostic text.

## Article-Level Fallback

Provider failure is handled at article granularity. When an article is unavailable or a provider attempt fails with a retryable provider error, LoreX automatically tries the next eligible provider according to priority/fill policy.

A provider failure must not force the whole release to restart from article zero. Already completed article state remains durable. A download fails only after the article's eligible provider set is exhausted or a non-retryable local error occurs.

Fallback behavior must be deterministic in tests and observable through counters.

## Streaming Writes

Article payloads are exposed to the downloader as chunk iterators/streams. The downloader writes chunks directly to a temporary on-disk article/output path and does not concatenate a full article body in Python memory.

The streaming contract must allow tests to prove bounded peak Python allocation as payload size increases. File handles are closed on all paths. Partial local files are either resumable where the protocol contract supports it or safely replaced on retry; they must never be mistaken for completed durable articles.

This PR does not implement PAR2, archive extraction, final media processing, or library import. It only produces download-stage files/state for PR 6 to consume.

## Concurrency

Concurrency limits are configuration-driven and bounded at two levels:

1. global active download/article work;
2. per-provider active connections.

The implementation must avoid creating one task per article for an arbitrarily large release. Work is pulled through bounded worker/semaphore structures so task count and memory depend on configured concurrency, not total article count.

Tests must verify the configured ceiling is never exceeded under concurrent synthetic loads.

## Progress Persistence Coalescing

High-frequency byte/article progress updates are accumulated in memory and persisted only when a configured byte threshold, time threshold, article completion, job state transition, or terminal condition requires a durable flush.

Terminal transitions always flush final progress. A crash may lose only the bounded in-memory progress interval, never durable completed-article truth.

Progress coalescing must measurably reduce PostgreSQL write frequency compared with persisting every chunk/event.

## Provider Health Metrics

LoreX retains bounded aggregate health metrics per provider, including at least:

- attempts;
- successful article fetches;
- failed article fetches;
- fallback count;
- bytes delivered;
- latency/elapsed-time aggregate sufficient for diagnostics.

Metrics must not contain credentials or raw article payloads. The design favors bounded aggregates over unbounded per-attempt history.

## Failure and Recovery Rules

PR 5 preserves these locked rules:

- PostgreSQL is authoritative for durable queue and article state;
- Redis loss must not lose durable work;
- workers cannot double-claim the same queued job;
- completed articles survive worker/app restart;
- provider fallback remains automatic;
- partial local data is never marked complete without the corresponding durable completion transition;
- bounded concurrency remains enforced during retries/fallback;
- local disk/write errors surface as job failures instead of being hidden by provider fallback;
- queue/downloader changes do not invoke importer/media-processing logic.

## Benchmark Contract

PR 1 established a 10,000-job queue round-trip p95 reference of approximately 107 ms. PR 5 adds durable PostgreSQL queue claim/transition scenarios and a deterministic streaming-downloader fixture.

Benchmarks must separately report:

- queue operations/second and p50/p95 for claim/transition work;
- downloader application CPU time/overhead;
- peak Python allocation and/or RSS for streamed payload processing;
- bytes processed/second for a synthetic provider with network delay disabled;
- an optional delayed-provider scenario clearly labeled as provider/network-bound rather than application throughput.

The streaming-memory benchmark must demonstrate that peak Python memory does not grow linearly with total payload size when chunk size and concurrency remain fixed. Progress-coalescing evidence must report persistence-write reduction without weakening terminal durability.

No performance gate may be satisfied by reducing required correctness work, skipping provider fallback, disabling durable article tracking, or lowering the benchmark workload.

## Testing and Merge Policy

Development follows red-green tests for:

- FIFO queue behavior without O(n) head removal;
- PostgreSQL claim exclusivity under concurrent workers;
- non-destructive durable job lifecycle;
- stale/in-progress recovery;
- completed-article resume behavior;
- provider priority and fill-server fallback;
- per-provider and global concurrency ceilings;
- chunked streaming writes and cleanup on failure;
- progress-persistence coalescing and terminal flushes;
- provider health counters;
- benchmark registration and regression gates.

Before integration, PR 5 must include fresh exact-head correctness tests, benchmark evidence, CPU/memory/database/disk regression review, and exact-head GitHub Actions success. The exact verified head is the only head eligible for merge.
