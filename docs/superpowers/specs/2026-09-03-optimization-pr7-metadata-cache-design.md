# LoreX Optimization PR 7 — Metadata Cache and Request Coalescing Design

## Status

Approved by the locked whole-app optimization program. This PR is serially based on Optimization PR 6 and must not include PR 8 UI/API responsiveness work.

## Goal

Make external book metadata lookup efficient and failure-tolerant while preserving LoreX's local metadata and confidence rules. Concurrent consumers asking for the same normalized book lookup must share one upstream request, repeated lookups must use a shared TTL cache, safe not-found results must be negatively cached, and artwork retrieval must not block critical metadata/read paths.

## Architecture

LoreX adds a focused `metadata` package with five boundaries:

1. `MetadataLookup` normalizes stable lookup identity without secrets.
2. `MetadataCache` stores positive/negative results. Redis is the shared production cache; an in-memory implementation is used for deterministic tests/fallback. Redis remains non-authoritative.
3. `RequestCoalescer` enforces one active upstream request per normalized key. Production uses a Redis lease plus cache recheck so multiple workers converge on one leader; a process-local lock prevents duplicate work when Redis is unavailable.
4. Provider adapters implement Open Library and Google Books using a common provider result contract and retry/backoff policy.
5. `MetadataResolver` orchestrates cache → coalescing → provider lookup → cache write → local-metadata fallback and schedules artwork asynchronously.

No durable book/library truth is stored only in Redis. Cache loss causes re-fetching, not data loss.

## Stable Lookup Keys

Keys are deterministic and namespace-scoped. Identifier precedence is:

1. ISBN-13
2. ISBN-10
3. ASIN
4. normalized `title + author`

Normalization case-folds text, collapses whitespace, removes surrounding whitespace, strips ISBN punctuation, and upper-cases ASIN. A cache key contains only normalized identifiers/text and a schema version, never API keys, credentials, bearer tokens, cookies, or full request URLs.

Example keys:

- `lorex:metadata:v1:isbn13:9780063279327`
- `lorex:metadata:v1:asin:B0ABC12345`
- `lorex:metadata:v1:title-author:project hail mary|andy weir`

## Cache Policy

Default TTLs:

- successful bibliographic metadata: 7 days
- safe not-found result: 15 minutes
- artwork fetch/processed result: 24 hours
- provider errors, timeouts, 429s, and 5xx responses: never negatively cached

Positive cache entries store normalized provider-neutral metadata, source/provider name, provider record id, identifiers, authors, title/subtitle, description, publication date, series hints when available, and artwork URL/reference. They do not store provider credentials or raw response headers.

Negative entries distinguish `not_found` from transient provider failure. A transient failure must not suppress a later retry.

## Request Coalescing

For each cache key:

1. Read cache.
2. On miss, acquire a process-local key lock.
3. Re-read cache.
4. If Redis is configured, attempt a short distributed lease (`SET NX EX`) for the key.
5. Lease winner performs provider lookup/retries, writes cache, and releases the lease with token-safe compare/delete.
6. Followers poll the cache with bounded backoff until the leader publishes a result or the lease expires, then may compete for the next lease.

The default lease is 15 seconds and follower wait is bounded to 20 seconds. Crashed leaders cannot permanently block a key.

## Provider Behavior

### Open Library

Use identifier endpoints when ISBN is available; otherwise use search by title/author. Parse only fields LoreX needs into the provider-neutral result.

### Google Books

Use `volumes` search with ISBN when present, otherwise `intitle` + `inauthor`. Optional API key is supplied only to the upstream request and is excluded from cache keys, structured results, exceptions, and logs.

### Retry / backoff

A single coalesced leader owns retries. Retry only transport failures, HTTP 429, and HTTP 5xx. Default maximum attempts: 3. Backoff is exponential with bounded jitter; `Retry-After` is honored when valid and capped. HTTP 4xx other than 429 is not retried. A safe provider `404`/empty result becomes `not_found`, not an exception storm.

Provider order is Open Library then Google Books by default. Future providers implement the same protocol.

## Local Metadata Fallback

`MetadataResolver.resolve()` accepts extracted local metadata. If all external providers are unavailable or transiently fail, the resolver returns the local candidate rather than discarding it. Local data remains available even when Redis and all upstream providers are down.

Low-confidence or ambiguous external matches are not silently promoted; PR 7 does not weaken existing identification confidence policy.

## Artwork

Metadata resolution returns artwork references immediately and schedules artwork fetch/processing through a bounded asynchronous scheduler. The critical metadata/read path never waits for image download, decode, resize, or disk write. Artwork failures do not fail bibliographic resolution.

Default artwork workers: 2. Queue depth is bounded; duplicate artwork keys coalesce. Artwork cache is disposable and may be regenerated.

## Observability

Expose counters for:

- metadata cache hits/misses
- negative cache hits
- coalesced followers
- upstream requests by provider
- provider retries and failures
- local-fallback uses
- artwork scheduled/deduplicated/dropped

Logs may include provider name, status class, attempt count, and a short hash of the normalized cache key. They must not include API keys or credential-bearing URLs.

## Benchmark Contract

PR 7 adds deterministic metadata benchmarks that do not depend on the public internet:

- cold same-key burst: at least 100 concurrent consumers, exactly one fake upstream request
- warm-cache burst: no upstream requests and materially lower p95 latency than uncached sequential provider latency
- negative-cache burst: one safe not-found upstream result, then zero additional upstream requests during TTL
- Redis-backed shared-cache/coalescing test in CI using the `redis:7-alpine` service

The performance claim is reduction in upstream work and latency, not synthetic public-provider speed.

## Failure / Recovery Rules

- Redis unavailable: use process-local coalescing/cache fallback and continue.
- Redis contents lost: re-fetch metadata; no durable truth is lost.
- Provider transient failure: do not negative-cache.
- Provider safe not-found: short negative cache allowed.
- Lease holder crashes: lease expiry permits recovery.
- Artwork failure: bibliographic result remains usable.
- Local extracted metadata survives all external failures.

## Scope Boundaries

Included: shared cache, distributed coalescing, Open Library/Google Books adapters, retries/backoff, local fallback, async artwork scheduling, observability, deterministic benchmarks and CI Redis service.

Excluded: UI query caching, React behavior, dashboard changes, route/code splitting, generalized recommendation metadata, multi-user quotas, or any PR 8 work.
