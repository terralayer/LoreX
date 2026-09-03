# LoreX Optimization PR 7 — Metadata Cache and Request Coalescing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add shared TTL metadata caching, same-key request coalescing, Open Library/Google Books adapters, resilient local fallback, asynchronous artwork scheduling, and deterministic performance evidence.

**Architecture:** `backend/lorex/metadata/` owns provider-neutral metadata contracts, normalized lookup keys, cache/coalescing implementations, provider clients, resolver orchestration, artwork scheduling, and metrics. Redis accelerates shared cache/coalescing but remains disposable; local metadata is always a usable fallback.

**Tech Stack:** Python 3.12, FastAPI-era synchronous services, httpx, redis-py, pytest, GitHub Actions Redis 7 service.

**Spec:** `docs/superpowers/specs/2026-09-03-optimization-pr7-metadata-cache-design.md`

## Global Constraints

- Product version remains `0.1.1 alpha` / Python `0.1.1a1` / npm `0.1.1-alpha.1`.
- PostgreSQL remains authoritative durable state.
- Redis stores disposable cache/lease state only.
- Cache keys and logs must never include credentials/API keys.
- One active upstream request per normalized cache key.
- Safe not-found TTL defaults to 15 minutes; positive metadata TTL defaults to 7 days.
- Provider transient failures are never negatively cached.
- Artwork work must not block metadata resolution.
- PR 8 UI/API responsiveness work is out of scope.

---

### Task 1: Metadata domain and stable key normalization

**Files:**
- Create: `backend/lorex/metadata/__init__.py`
- Create: `backend/lorex/metadata/model.py`
- Test: `tests/test_metadata_model.py`

**Interfaces:**
- Produces: `MetadataLookup`, `BookMetadata`, `ProviderOutcome`, `normalize_lookup_key(lookup) -> str`.

- [ ] Write failing tests proving ISBN punctuation normalization, ASIN casing, title/author whitespace/case normalization, precedence, and absence of API-key material from keys.
- [ ] Run `pytest tests/test_metadata_model.py -q` and verify RED because the package/types do not exist.
- [ ] Implement immutable slot dataclasses and deterministic `lorex:metadata:v1:*` keys.
- [ ] Run the focused test and the full backend suite.
- [ ] Commit `feat: add metadata lookup model`.

### Task 2: Cache contract and in-memory TTL implementation

**Files:**
- Create: `backend/lorex/metadata/cache.py`
- Test: `tests/test_metadata_cache.py`

**Interfaces:**
- Produces: `MetadataCache` protocol, `CacheEntry`, `InMemoryMetadataCache` with `get`, `set_found`, `set_not_found`, and `delete`.

- [ ] Write failing tests for positive TTL, negative TTL, expiration using injected clock, no negative caching of failures, and serialized provider-neutral data.
- [ ] Verify RED.
- [ ] Implement the smallest thread-safe TTL cache with injected monotonic clock.
- [ ] Run focused/full tests.
- [ ] Commit `feat: add metadata TTL cache contract`.

### Task 3: Redis shared cache and distributed lease

**Files:**
- Modify: `pyproject.toml`
- Create: `backend/lorex/metadata/redis_cache.py`
- Test: `tests/test_metadata_redis.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `RedisMetadataCache`, `RedisLeaseCoordinator`, `Lease`.

- [ ] Add failing tests using a real CI Redis service for positive/negative round-trip, expiry, `SET NX EX` leader selection, token-safe release, and follower recovery after lease expiry.
- [ ] Verify RED.
- [ ] Move `httpx` to runtime dependencies and add `redis>=6,<7`; add Redis 7 service/`LOREX_REDIS_URL` to backend and benchmark jobs.
- [ ] Implement JSON cache values with schema version and Redis lease keys derived only from normalized cache-key hashes.
- [ ] Implement Lua/token-safe compare-delete lease release.
- [ ] Run focused/full tests against PostgreSQL+Redis CI.
- [ ] Commit `feat: add Redis metadata cache and lease`.

### Task 4: Provider retry/backoff and adapters

**Files:**
- Create: `backend/lorex/metadata/providers.py`
- Test: `tests/test_metadata_providers.py`

**Interfaces:**
- Produces: `MetadataProvider` protocol, `ProviderClient`, `OpenLibraryProvider`, `GoogleBooksProvider`, `ProviderError`.

- [ ] Write failing tests with `httpx.MockTransport`: ISBN query construction, title/author fallback, parsing, safe not-found, retry on 429/5xx/transport error, no retry on other 4xx, Retry-After cap, and API key excluded from exceptions/results.
- [ ] Verify RED.
- [ ] Implement provider-neutral parsing and injectable sleeper/jitter for deterministic retry tests.
- [ ] Run focused/full tests.
- [ ] Commit `feat: add resilient metadata providers`.

### Task 5: Same-key coalescing resolver and local fallback

**Files:**
- Create: `backend/lorex/metadata/resolver.py`
- Create: `backend/lorex/metadata/metrics.py`
- Test: `tests/test_metadata_resolver.py`

**Interfaces:**
- Produces: `MetadataResolver.resolve(lookup, local_metadata=None) -> BookMetadata | None`, `MetadataMetrics`.

- [ ] Write failing concurrent tests proving 100 same-key callers produce exactly one provider request, cache recheck after lock, negative-cache reuse, transient failures are retried later, and local metadata is returned if all providers fail.
- [ ] Add distributed-coalescing test with two resolver instances sharing Redis and verify one upstream request total.
- [ ] Verify RED.
- [ ] Implement per-key local locks plus Redis lease leadership/follower cache polling with bounded wait.
- [ ] Implement provider fallback order and metrics counters.
- [ ] Ensure exceptions/loggable error strings contain provider/status only, never key credentials.
- [ ] Run focused/full tests.
- [ ] Commit `feat: coalesce metadata requests`.

### Task 6: Bounded asynchronous artwork scheduler

**Files:**
- Create: `backend/lorex/metadata/artwork.py`
- Test: `tests/test_metadata_artwork.py`
- Modify: `backend/lorex/metadata/resolver.py`

**Interfaces:**
- Produces: `ArtworkScheduler.submit(cache_key, url) -> bool`, bounded worker/queue behavior.

- [ ] Write failing tests proving submit returns without waiting for fetch, duplicate keys coalesce, max worker count is 2 by default, queue is bounded, failures do not change bibliographic results.
- [ ] Verify RED.
- [ ] Implement a bounded executor/queue with nonblocking submission and disposable artwork-result cache hooks.
- [ ] Wire resolver success to schedule artwork after metadata is available.
- [ ] Run focused/full tests.
- [ ] Commit `feat: schedule metadata artwork asynchronously`.

### Task 7: Metadata benchmark and regression evidence

**Files:**
- Create: `benchmarks/metadata.py`
- Create: `benchmarks/run_pr7.py`
- Test: `tests/test_metadata_benchmark.py`
- Modify: `.github/workflows/ci.yml`
- Create: `docs/performance/optimization-pr7-metadata-cache.md`

**Interfaces:**
- Produces deterministic report `benchmark-results/pr7-metadata.{json,md}`.

- [ ] Write failing benchmark-contract tests requiring cold 100-consumer same-key burst, warm cache, negative cache, upstream-call counts, p50/p95, and coalesced-follower counts.
- [ ] Verify RED.
- [ ] Implement fake-latency provider and deterministic benchmark runner; do not call public APIs.
- [ ] Add `python -m benchmarks.run_pr7 --output benchmark-results` to CI and append report to job summary.
- [ ] Run benchmark and compare: cold burst upstream calls must equal 1; warm/negative repeat upstream calls must equal 0; warm p95 must be materially lower than fake provider latency.
- [ ] Record CPU/memory/network-request regression review and exact measurements.
- [ ] Commit `perf: publish PR7 metadata benchmark evidence`.

### Task 8: Final verification and integration

**Files:**
- Review all PR 7 changes only.

- [ ] Run full backend correctness suite with PostgreSQL+Redis.
- [ ] Run frontend production build unchanged.
- [ ] Run baseline benchmark plus PR 6 and PR 7 benchmark jobs.
- [ ] Verify uploaded artifacts/reports and exact branch head.
- [ ] Review changed files for PR 8 scope leakage and credential logging.
- [ ] Open/update the PR with measured evidence.
- [ ] Require fresh exact-head CI green before squash merge.
