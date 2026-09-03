# Optimization PR 4 Fast Search and Lightweight Read APIs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace full-catalog release reads with indexed PostgreSQL search, bounded pagination, lightweight projections, and measurable 1M-release search latency.

**Architecture:** PostgreSQL remains authoritative. Add `pg_trgm` GIN indexes for substring search fields, expose a repository `search_page()` that selects only summary columns, and keep heavyweight release/NZB data on detail/grab paths. API parameters are bounded and explicit. Benchmark the real PostgreSQL query at one million deterministic rows and require p95 <150 ms for the representative selective tail-search query.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL 16, Alembic, psycopg 3, pytest, existing LoreX benchmark harness.

**Spec:** `docs/superpowers/specs/2026-09-02-optimization-pr4-fast-search-apis-design.md`

## Global Constraints

- Product remains LoreX `0.1.1 alpha`.
- PostgreSQL remains authoritative state; Redis is not authoritative.
- Normal search/list endpoints must not materialize all release rows.
- Search/list responses use lightweight projections separate from detail objects.
- Server-side pagination and explicit sort/filter parameters are required.
- Search p95 is evaluated at 1,000,000 PostgreSQL releases.
- Correctness tests are hard gates; benchmark evidence is required before integration.
- PR 5 queue/downloader behavior is out of scope.

---

### Task 1: Trigram search migration

**Files:**
- Create: `migrations/versions/0002_release_search_indexes.py`
- Test: `tests/test_database_schema.py`

**Interfaces:**
- Produces PostgreSQL extension `pg_trgm` and GIN trigram indexes for `normalized_title`, `normalized_author`, `narrator`, and `source_subject`.

- [ ] Add a failing schema test that queries `pg_extension` and `pg_indexes` after migrations and requires the extension/index names.
- [ ] Run the schema test and confirm RED because migration `0002` does not exist.
- [ ] Add the Alembic migration using `CREATE EXTENSION IF NOT EXISTS pg_trgm` and `gin_trgm_ops` indexes.
- [ ] Run the schema test and full backend suite; confirm GREEN.
- [ ] Commit the migration and test.

### Task 2: Lightweight paged repository search

**Files:**
- Create: `backend/lorex/search.py`
- Modify: `backend/lorex/postgres_repository.py`
- Test: `tests/test_postgres_search.py`

**Interfaces:**
- Produces `ReleaseSummary`, `ReleaseSearchPage`, and `ReleaseSearchQuery`.
- Produces `PostgresReleaseRepository.search_page(query: ReleaseSearchQuery) -> ReleaseSearchPage`.

- [ ] Write RED tests for bounded page sizes, offset pagination, deterministic sort/order, `format`, `download_status`, and `import_status` filtering, summary-only fields, and total count.
- [ ] Implement immutable dataclasses/enums in `search.py`; validate `limit` 1..100 and nonnegative offset.
- [ ] Implement `search_page()` with separate filtered count and summary-column select. For non-empty `q`, use trigram-compatible `ILIKE '%needle%'` predicates. Select only id/title/author/narrator/format/size/completion plus status/date fields needed by list UI; do not select `nzb` or `source_subject` into returned objects.
- [ ] Use a strict sort-field map rather than interpolating user input. Add stable `id` tie-breaking.
- [ ] Run targeted and full backend tests; commit GREEN implementation.

### Task 3: Bounded FastAPI release read contract

**Files:**
- Modify: `backend/lorex/api/releases.py`
- Test: `tests/test_release_api.py`

**Interfaces:**
- `GET /api/releases/search?q=&limit=50&offset=0&sort=title&order=asc&format=&download_status=&import_status=` returns `{total, limit, offset, results}`.
- `GET /api/releases/{release_id}` returns the full release detail object.

- [ ] Write RED API tests requiring max `limit=100`, validation errors for invalid sort/order/limit, pagination metadata, lightweight result shape, and full detail endpoint.
- [ ] Add Pydantic response models and explicit query parameter validation.
- [ ] Route PostgreSQL-backed search through `search_page()`. Keep a bounded compatibility path for in-memory test/dev repositories without changing production PostgreSQL semantics.
- [ ] Add full detail endpoint before the existing `/releases/{release_id}/nzb` route semantics are affected; verify 404 behavior.
- [ ] Run targeted API tests and full backend suite; commit GREEN implementation.

### Task 4: Bounded dashboard aggregates

**Files:**
- Modify: `backend/lorex/postgres_repository.py`
- Modify: `backend/lorex/api/library.py`
- Test: `tests/test_postgres_search.py`
- Test: `tests/test_release_api.py`

**Interfaces:**
- Produces `PostgresReleaseRepository.dashboard_summary() -> DashboardSummary`.
- Produces a lightweight dashboard API response with aggregate counts only.

- [ ] Write RED repository and API tests proving dashboard counts are computed without materializing release rows or issuing per-row lookups.
- [ ] Add an immutable `DashboardSummary` projection and implement aggregate `COUNT` queries grouped by the status fields required by the dashboard.
- [ ] Expose the aggregate response through the existing API router without returning release detail objects.
- [ ] Run targeted API/repository tests and the full backend suite; commit GREEN implementation.

### Task 5: One-million-row PostgreSQL search benchmark and hard gate

**Files:**
- Modify: `benchmarks/scenarios.py`
- Modify: `benchmarks/run_baseline.py`
- Test: `tests/test_postgres_benchmarks.py`
- Test: `tests/test_benchmark_runner.py`

**Interfaces:**
- Produces scenario `postgres_release_search` at scales 100,000 and 1,000,000.
- CI profile enforces representative 1M selective-search p95 <150 ms.

- [ ] Write RED benchmark-contract tests requiring the new scenario and 1M CI scale.
- [ ] Seed deterministic benchmark rows efficiently with PostgreSQL `generate_series`/set-based SQL so fixture creation is excluded from measured search latency and does not depend on the application bulk-ingest rate.
- [ ] Run `ANALYZE releases` after seeding, warm the representative query, then measure `search_page()` against a unique near-tail needle.
- [ ] Add a benchmark gate that exits nonzero if the 1M selective search p95 is >=150 ms; retain JSON/Markdown/artifact diagnostics.
- [ ] Run the full CI benchmark. If the gate fails, inspect `EXPLAIN (ANALYZE, BUFFERS)` and tune indexes/query shape rather than weakening the target.
- [ ] Commit only after the 1M gate is GREEN.

### Task 6: Performance record and exact-head verification

**Files:**
- Create: `docs/performance/optimization-pr4-fast-search-apis.md`

**Interfaces:**
- Records before/after search latency, query plan evidence, response bounding, and any hosted-runner caveats.

- [ ] Capture fresh 100K/1M PostgreSQL search p50/p95 and relevant regression scenarios from the exact implementation head.
- [ ] Document the legacy ~2.9s 1M in-memory linear-search reference versus the new PostgreSQL paged search without implying fixture-generation speed is search speed.
- [ ] Review changed files against PR-4 scope; ensure no queue/downloader/importer work leaked in.
- [ ] Run fresh exact-head CI: PostgreSQL migrations/tests, frontend build, benchmark gate, summary, artifact.
- [ ] Integrate only the exact verified head, then verify `main`.
