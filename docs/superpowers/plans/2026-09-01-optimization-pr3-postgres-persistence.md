# LoreX Optimization PR 3 PostgreSQL Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LoreX's in-memory authoritative repositories with PostgreSQL-backed durable storage, migrations, bulk ingestion, and the indexed access paths required by the locked optimization design.

**Architecture:** Add SQLAlchemy 2.x models and Alembic migrations over PostgreSQL 16, with repository adapters that preserve the existing application-facing interfaces where practical. PostgreSQL is authoritative; Redis remains optional/ephemeral. Keep PR 4 search pagination and API projection redesign out of scope while ensuring PR 3 creates the indexes PR 4 will consume.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, psycopg 3, Alembic, PostgreSQL 16, pytest.

**Spec:** `docs/superpowers/specs/2026-09-01-whole-app-optimization-design.md`

## Global Constraints

- Product version remains `0.1.1 alpha` / Python `0.1.1a1`.
- PostgreSQL remains authoritative persistent state; Redis must not become authoritative.
- Preserve PR 2 streaming/checkpoint/dedupe behavior.
- Bulk ingestion must avoid one transaction per row.
- Required indexes: normalized release title, normalized author, narrator, ISBN-10/13, ASIN, series/position, posted date, message ID, release fingerprint, wanted fields, and download/import status fields.
- PR 4 pagination/search API redesign is out of scope.
- Every behavior change follows red-green tests and exact-head CI verification.

---

### Task 1: Database Foundation and Migrations

**Files:**
- Modify: `pyproject.toml`
- Create: `alembic.ini`
- Create: `backend/lorex/db.py`
- Create: `backend/lorex/db_models.py`
- Create: `migrations/env.py`
- Create: `migrations/versions/0001_postgres_persistence.py`
- Test: `tests/test_database_schema.py`

**Interfaces:**
- Produces: `create_engine_from_url(url: str)`, `session_factory(engine)`, ORM models for releases/articles/checkpoints/books/jobs and indexed metadata/status columns.

- [ ] **Step 1: Write failing schema tests** asserting the migration creates tables and named indexes including `ix_releases_normalized_title`, `ix_releases_normalized_author`, `ix_releases_narrator`, `ix_releases_isbn10`, `ix_releases_isbn13`, `ix_releases_asin`, `ix_releases_series_position`, `ix_releases_posted_at`, `ux_release_articles_message_id`, `ux_releases_fingerprint`, `ix_releases_wanted_match`, `ix_download_jobs_status`, and `ix_import_jobs_status`.
- [ ] **Step 2: Run** `pytest tests/test_database_schema.py -q` and verify failure because database infrastructure does not exist.
- [ ] **Step 3: Add SQLAlchemy/Alembic/psycopg dependencies, models, engine/session helpers, and migration.** Normalize searchable fields on write; keep message IDs and fingerprints unique.
- [ ] **Step 4: Run** `pytest tests/test_database_schema.py -q` against PostgreSQL and verify pass.
- [ ] **Step 5: Commit** `feat: add postgres schema and migrations`.

### Task 2: PostgreSQL Release Repository and Atomic Index Batches

**Files:**
- Create: `backend/lorex/postgres_repository.py`
- Modify: `backend/lorex/services/indexing.py`
- Test: `tests/test_postgres_release_repository.py`

**Interfaces:**
- Produces: `PostgresReleaseRepository` implementing `add`, `get`, `search`, `commit_index_batch`, `articles_for`, `checkpoint_for`, `get_cached_nzb`, and `cache_nzb`.

- [ ] **Step 1: Write failing integration tests** proving a 512-release batch is inserted in one transaction, article refs are durable, duplicate fingerprints/message IDs do not duplicate rows, and checkpoint regression rolls back the entire batch.
- [ ] **Step 2: Run** `pytest tests/test_postgres_release_repository.py -q` and verify intended failures.
- [ ] **Step 3: Implement bulk insert/upsert and transactional checkpoint persistence.** Use one session transaction per batch and database uniqueness for race-safe dedupe.
- [ ] **Step 4: Run repository tests plus `tests/test_streaming_indexer.py`** and verify all pass.
- [ ] **Step 5: Commit** `feat: persist indexed releases in postgres`.

### Task 3: Durable Library and Job Repositories

**Files:**
- Modify: `backend/lorex/postgres_repository.py`
- Modify: `backend/lorex/main.py`
- Test: `tests/test_postgres_state_repositories.py`

**Interfaces:**
- Produces: `PostgresLibraryRepository`, `PostgresJobRepository`; application container selects PostgreSQL adapters when `LOREX_DATABASE_URL` is configured.

- [ ] **Step 1: Write failing tests** proving library books and queued jobs survive repository/container recreation and FIFO ordering is preserved without list `pop(0)`.
- [ ] **Step 2: Run** `pytest tests/test_postgres_state_repositories.py -q` and verify intended failures.
- [ ] **Step 3: Implement durable repositories and application wiring**, retaining in-memory adapters only as explicit test/dev fallback.
- [ ] **Step 4: Run full backend tests** and verify existing API/download/import behavior remains green.
- [ ] **Step 5: Commit** `feat: make postgres authoritative app state`.

### Task 4: PostgreSQL Benchmark Coverage

**Files:**
- Modify: `benchmarks/scenarios.py`
- Modify: `benchmarks/run_baseline.py`
- Create: `docs/performance/pr3-postgres-persistence.md`
- Test: `tests/test_benchmarks.py`

**Interfaces:**
- Produces benchmark scenarios `postgres_bulk_index` and `postgres_index_lookup` with database rows/sec, p50/p95, and scenario-specific Python peak memory.

- [ ] **Step 1: Write failing benchmark-registry tests** requiring PostgreSQL scenarios and deterministic scale configuration.
- [ ] **Step 2: Run** `pytest tests/test_benchmarks.py -q` and verify failure.
- [ ] **Step 3: Add database benchmark scenarios** measuring batch persistence and indexed point/filter lookups without crediting PR 4's future search work.
- [ ] **Step 4: Run benchmark profile against PostgreSQL** and document before/after database persistence evidence plus CPU/memory/API regression review.
- [ ] **Step 5: Commit** `perf: benchmark postgres persistence`.

### Task 5: CI PostgreSQL Gate and Final Verification

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- CI backend and benchmark jobs receive PostgreSQL 16 service and `LOREX_DATABASE_URL`.

- [ ] **Step 1: Add PostgreSQL service/health check** to relevant CI jobs and run migrations before tests/benchmarks.
- [ ] **Step 2: Run the full correctness suite**, frontend production build, migrations, and full benchmark job.
- [ ] **Step 3: Confirm no unacceptable regression** in PR 2's 100K header throughput/memory and record PostgreSQL batch persistence metrics.
- [ ] **Step 4: Open PR 3 against `main` only after exact-head CI is green.**
- [ ] **Step 5: Merge only with the exact verified head SHA pinned.**
