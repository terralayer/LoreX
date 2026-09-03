# Optimization PR 4: Fast Search and Lightweight Read APIs

## Result

LoreX `0.1.1 alpha` now serves bounded release-search pages from PostgreSQL instead of materializing and scanning the complete release catalog. The representative selective search at 1,000,000 releases measured **39.344 ms p50** and **42.374 ms p95**, passing the locked **p95 <150 ms** gate.

The original PR 1 in-memory reference measured **2,926.132 ms p50** and **3,014.778 ms p95** at the same one-million-release scale. These workloads establish an approximately **71.1x p95 latency reduction** for the representative selective read. Fixture generation is excluded from both reported search timings.

## Read Contract

- `GET /api/releases/search` accepts a search term, `limit` from 1 through 100, nonnegative `offset`, closed sort/order values, and format/download/import filters.
- Results contain lightweight summary fields only. They do not contain NZB payloads or source subjects.
- `GET /api/releases/{release_id}` retains full detail access, including the NZB and source subject fields.
- Every PostgreSQL page uses a filtered count query and a bounded summary-column query with a stable ID tie-breaker.
- `GET /api/library/dashboard` returns aggregate release and status counts without loading release rows or issuing per-row lookups.

## PostgreSQL Query Evidence

The one-million-row fixture was inserted with set-based `generate_series` SQL, followed by `ANALYZE`; setup was outside the measured region. Search used a deterministic MD5 token present in exactly one near-tail source subject. The query plan used a `BitmapOr` over all four GIN trigram indexes:

- `ix_releases_normalized_title_trgm`
- `ix_releases_normalized_author_trgm`
- `ix_releases_narrator_trgm`
- `ix_releases_source_subject_trgm`

On GitHub's hosted PostgreSQL 16 service, the recorded count query executed in **17.059 ms** and the bounded page query in **17.200 ms**. Each touched 936 shared buffers and returned one exact result.

## Benchmark Measurements

| Scenario | Scale | p50 ms | p95 ms | Gate |
| --- | ---: | ---: | ---: | --- |
| Legacy in-memory release search | 1,000,000 | 2,926.132 | 3,014.778 | Reference only |
| PostgreSQL selective release search | 1,000,000 | 39.344 | 42.374 | Pass: p95 <150 ms |

The same run's 100,000-row PostgreSQL sample measured 296.164 ms p50 and 304.220 ms p95. This smaller bulk-loaded fixture had not crossed PostgreSQL's automatic GIN pending-list cleanup threshold; it is retained transparently as a hosted-runner fixture caveat and is not substituted for the locked one-million-row result. An attempted explicit post-seed `VACUUM (ANALYZE)` was rejected by the hosted service because its shared-memory filesystem could not grow by roughly 64 MiB, so the benchmark keeps the approved `ANALYZE`-only setup.

## Verification

- GitHub Actions run `33712137501` on commit `789911c` passed migrations, the complete backend test suite, frontend production build, and the 1M performance gate.
- Its independently triggered companion run `33712140300` also passed on the same commit.
- The branch diff is limited to the PR 4 design/plan, trigram migration, search projections/repository, release and dashboard APIs, benchmark coverage, and tests. Queue, downloader, importer, metadata, and frontend optimization behavior remain out of scope.
- Final exact-head GitHub Actions run `33712682910` on commit `47e5b20ced912d03eba88b3ad176192aee2d1be2` passed migrations, backend tests, frontend production build, the benchmark gate, benchmark summary publication, and benchmark artifact upload.
