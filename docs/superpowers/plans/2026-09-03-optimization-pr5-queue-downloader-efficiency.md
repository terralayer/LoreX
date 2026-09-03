# Optimization PR 5 Queue and Downloader Efficiency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace destructive/simple download queuing with durable resumable PostgreSQL work coordination and a bounded streaming multi-provider downloader whose CPU, memory, queue, and persistence behavior is benchmarked independently from provider/network delay.

**Architecture:** PostgreSQL remains authoritative for download jobs and article progress. Workers claim oldest queued jobs with `FOR UPDATE SKIP LOCKED`, persist resumable per-article state, and stream article chunks to disk through a provider abstraction with bounded global/per-provider concurrency and article-level fallback. In-memory repositories remain deterministic compatibility implementations for tests/dev, while Redis remains optional and non-authoritative.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL 16, Alembic, psycopg 3, pytest, `asyncio`, standard-library TLS/socket abstractions for production-facing provider contracts, existing LoreX benchmark harness.

**Spec:** `docs/superpowers/specs/2026-09-03-optimization-pr5-queue-downloader-efficiency-design.md`

## Global Constraints

- Product remains LoreX `0.1.1 alpha`; Python package `0.1.1a1`; npm package `0.1.1-alpha.1`.
- PostgreSQL remains authoritative durable state; Redis must never be required for recovery.
- Queue ordering is oldest-first by `created_order`.
- Normal dequeue/claim behavior must not delete durable job rows.
- No O(n) queue head removal such as list `pop(0)`.
- Download/article concurrency and provider connection counts are always bounded by configuration.
- Production provider definitions require TLS; credentials must never appear in logs, metrics, persisted diagnostics, or benchmark fixtures.
- Provider fallback is article-level and automatic.
- Article payloads are streamed to disk; full article bodies are never concatenated in Python memory.
- Progress writes are coalesced; terminal state and completed-article truth remain durable.
- PR 6 PAR2/extraction/FFmpeg/importer work, PR 7 metadata work, and PR 8 frontend work are out of scope.
- Every behavior change follows red-green tests; exact-head CI and fresh benchmark evidence are required before merge.

---

### Task 1: Durable queue and article-state schema

**Files:**
- Create: `migrations/versions/0003_download_queue_efficiency.py`
- Modify: `backend/lorex/db_models.py`
- Modify: `backend/lorex/domain.py`
- Test: `tests/test_database_schema.py`
- Test: `tests/test_download_queue.py`

**Interfaces:**
- Produces `DownloadArticleState` domain records.
- Extends `DownloadJobRow` with claim/progress/recovery fields.
- Produces `DownloadArticleRow` with durable per-job/per-article state.
- Produces `ProviderHealthRow` with bounded aggregate provider counters.

- [ ] **Step 1: Write failing schema/domain tests** requiring download-job lifecycle fields (`claimed_at`, `claimed_by`, `bytes_completed`, `articles_completed`, `updated_at`), `download_articles`, and `provider_health` tables plus required indexes/constraints.

```python
def test_download_efficiency_schema_exists(engine):
    tables = inspect(engine).get_table_names()
    assert "download_articles" in tables
    assert "provider_health" in tables
    columns = {column["name"] for column in inspect(engine).get_columns("download_jobs")}
    assert {"claimed_at", "claimed_by", "bytes_completed", "articles_completed", "updated_at"} <= columns
```

- [ ] **Step 2: Run targeted schema tests and confirm RED** because migration `0003` and models do not exist.

Run: `pytest tests/test_database_schema.py tests/test_download_queue.py -q`

- [ ] **Step 3: Add domain state types** in `backend/lorex/domain.py`.

```python
@dataclass(frozen=True, slots=True)
class DownloadArticleState:
    job_id: str
    message_id: str
    status: str = "pending"
    bytes_completed: int = 0
    provider: str | None = None
    attempts: int = 0
```

- [ ] **Step 4: Add SQLAlchemy models** in `backend/lorex/db_models.py` with a uniqueness constraint on `(job_id, message_id)`, an index on `(job_id, status, created_order)`, and one row per provider in `provider_health`.

- [ ] **Step 5: Add Alembic migration `0003_download_queue_efficiency`** with `down_revision = "0002_release_search_indexes"`, additive job columns, `download_articles`, and `provider_health`; downgrade removes only PR5 objects/columns.

- [ ] **Step 6: Run targeted and full backend tests; confirm GREEN.**

Run: `pytest tests/test_database_schema.py tests/test_download_queue.py -q && pytest -q`

- [ ] **Step 7: Commit.**

Commit message: `feat: add durable download queue state`

---

### Task 2: Non-destructive durable queue lifecycle and recovery

**Files:**
- Modify: `backend/lorex/repository.py`
- Modify: `backend/lorex/postgres_repository.py`
- Test: `tests/test_download_queue.py`
- Test: `tests/test_postgres_queue.py`

**Interfaces:**
- Produces `JobRepository.claim_next(worker_id: str) -> DownloadJob | None`.
- Produces `JobRepository.mark_completed(job_id: str) -> None` and `mark_failed(job_id: str) -> None`.
- Produces `PostgresJobRepository.claim_next(worker_id: str) -> DownloadJob | None` using `FOR UPDATE SKIP LOCKED`.
- Produces `recover_stale(stale_before: datetime) -> int` to return stale `downloading` jobs to `queued`.
- `pop_next()` remains only as a compatibility wrapper over claim behavior if existing callers still require it; it must not delete PostgreSQL rows.

- [ ] **Step 1: Write RED tests** for FIFO claim order, `deque.popleft()` compatibility behavior, durable row retention after claim, completed/failed transitions, two-worker claim exclusivity, and stale recovery.

```python
def test_in_memory_queue_uses_fifo_claim_without_list_head_shift():
    jobs = JobRepository()
    jobs.add(DownloadJob("j1", "r1"))
    jobs.add(DownloadJob("j2", "r2"))
    assert jobs.claim_next("worker-a").id == "j1"
    assert jobs.claim_next("worker-a").id == "j2"
```

```python
def test_postgres_workers_cannot_claim_same_job(repo_factory):
    first = repo_factory().claim_next("worker-a")
    second = repo_factory().claim_next("worker-b")
    assert first is not None
    assert second is None
```

- [ ] **Step 2: Run queue tests and confirm RED.**

Run: `pytest tests/test_download_queue.py tests/test_postgres_queue.py -q`

- [ ] **Step 3: Replace in-memory list queue with `collections.deque`** and implement explicit lifecycle transitions without linear head removal.

- [ ] **Step 4: Implement PostgreSQL claim** as one transaction selecting oldest `queued` row ordered by `created_order`, locking with `skip_locked=True`, then updating status/claim fields instead of deleting.

- [ ] **Step 5: Implement terminal transitions and stale recovery** with bounded update statements and no duplicate job creation.

- [ ] **Step 6: Run targeted/full tests; confirm GREEN.**

Run: `pytest tests/test_download_queue.py tests/test_postgres_queue.py -q && pytest -q`

- [ ] **Step 7: Commit.**

Commit message: `feat: make download queue durable and resumable`

---

### Task 3: Durable article progress repository and write coalescing

**Files:**
- Create: `backend/lorex/downloader/progress.py`
- Modify: `backend/lorex/postgres_repository.py`
- Modify: `backend/lorex/repository.py`
- Test: `tests/test_download_progress.py`

**Interfaces:**
- Produces repository methods:
  - `ensure_articles(job_id: str, articles: Iterable[ArticleHeader]) -> int`
  - `pending_articles(job_id: str) -> tuple[DownloadArticleState, ...]`
  - `mark_article_started(job_id: str, message_id: str, provider: str) -> None`
  - `mark_article_completed(job_id: str, message_id: str, provider: str, bytes_completed: int) -> None`
  - `mark_article_failed(job_id: str, message_id: str, provider: str) -> None`
- Produces `ProgressCoalescer(byte_threshold: int, time_threshold_seconds: float)` with `record(...)`, `should_flush(...)`, and `flush(...)` behavior.

- [ ] **Step 1: Write RED tests** proving completed articles are skipped on restart, in-progress articles become retryable, progress events below thresholds do not persist, byte/time thresholds do persist, and terminal/article-complete events force a flush.

```python
def test_progress_coalescer_reduces_chunk_writes(fake_clock, sink):
    coalescer = ProgressCoalescer(byte_threshold=1024, time_threshold_seconds=5, clock=fake_clock)
    for _ in range(7):
        coalescer.record(100)
    assert sink.write_count == 0
    coalescer.record(400)
    coalescer.flush_if_needed(sink)
    assert sink.write_count == 1
```

- [ ] **Step 2: Run targeted tests and confirm RED.**

Run: `pytest tests/test_download_progress.py -q`

- [ ] **Step 3: Implement durable article initialization/state transitions** using bulk insert-on-conflict and targeted updates; completed articles must never revert during normal retry.

- [ ] **Step 4: Implement `ProgressCoalescer`** with injected monotonic clock for deterministic tests and terminal flush semantics.

- [ ] **Step 5: Run targeted/full tests; confirm GREEN.**

Run: `pytest tests/test_download_progress.py -q && pytest -q`

- [ ] **Step 6: Commit.**

Commit message: `feat: persist resumable article progress`

---

### Task 4: Provider contracts, bounded pools, health metrics, and fallback

**Files:**
- Create: `backend/lorex/downloader/provider.py`
- Create: `backend/lorex/downloader/health.py`
- Modify: `backend/lorex/postgres_repository.py`
- Test: `tests/test_downloader_providers.py`

**Interfaces:**
- Produces immutable `ProviderConfig(name, host, port=563, priority=100, fill_server=False, max_connections=4, enabled=True, tls=True)`.
- Produces `ArticleProvider` protocol with `stream_article(message_id: str) -> Iterator[bytes]`.
- Produces `ProviderPool` enforcing `max_connections`.
- Produces `ProviderSet` ordered primary-before-fill, then ascending priority/name.
- Produces provider aggregate metrics update API: `record_provider_attempt(name, *, success, fallback, byte_count, elapsed_ms)`.

- [ ] **Step 1: Write RED tests** for TLS-required production configs, deterministic provider ordering, per-provider max active connections, primary-before-fill behavior, fallback after retryable unavailable/provider errors, no fallback for local disk errors, and bounded health aggregates.

- [ ] **Step 2: Run targeted tests and confirm RED.**

Run: `pytest tests/test_downloader_providers.py -q`

- [ ] **Step 3: Implement provider configuration and protocols** without embedding credentials in the config representation or `repr`.

- [ ] **Step 4: Implement bounded provider pools** with standard-library synchronization primitives; tests use deterministic fake providers rather than external NNTP.

- [ ] **Step 5: Implement ordered fallback selection** and explicit retryable provider exceptions such as `ArticleUnavailable` and `ProviderTemporaryError`.

- [ ] **Step 6: Implement bounded aggregate health updates** in memory and PostgreSQL; no unbounded attempt-history table.

- [ ] **Step 7: Run targeted/full tests; confirm GREEN.**

Run: `pytest tests/test_downloader_providers.py -q && pytest -q`

- [ ] **Step 8: Commit.**

Commit message: `feat: add bounded provider pools and fallback`

---

### Task 5: Streaming downloader engine with bounded concurrency and resume

**Files:**
- Create: `backend/lorex/downloader/engine.py`
- Modify: `backend/lorex/downloader/__init__.py`
- Modify: `backend/lorex/main.py`
- Test: `tests/test_streaming_downloader.py`

**Interfaces:**
- Produces `DownloaderConfig(download_root: Path, max_active_articles: int = 8, progress_byte_threshold: int = 1_048_576, progress_time_threshold_seconds: float = 1.0)`.
- Produces `StreamingDownloader.download_job(job: DownloadJob, release: IndexedRelease, articles: Iterable[ArticleHeader]) -> DownloadResult`.
- Consumes `ProviderSet`, durable job/article repository, `ProgressCoalescer`.
- Writes article chunks directly to temporary paths and atomically promotes completed article/output stage files.

- [ ] **Step 1: Write RED tests** proving chunked writes without whole-payload concatenation, bounded global active articles, per-provider limits under concurrent jobs, completed-article resume skip, fallback on one article without restarting prior completed articles, cleanup of partial file after failed retry, and terminal job state/progress flush.

```python
def test_large_article_is_streamed_with_bounded_python_memory(tmp_path):
    provider = RepeatingChunkProvider(chunk=b"x" * 65536, chunks=256)
    downloader = build_downloader(provider, tmp_path, max_active_articles=2)
    result = downloader.download_job(job, release, [article])
    assert result.size == 16 * 1024 * 1024
    assert provider.max_materialized_chunks == 1
```

- [ ] **Step 2: Run targeted tests and confirm RED.**

Run: `pytest tests/test_streaming_downloader.py -q`

- [ ] **Step 3: Implement bounded worker loop** that pulls article work incrementally; do not create a task/future for every article in an unbounded release.

- [ ] **Step 4: Implement streamed temporary-file writes** using `for chunk in provider.stream_article(...): file.write(chunk)` and atomic completion markers/state transitions.

- [ ] **Step 5: Integrate resume/fallback/progress/health behavior** while keeping PR6 post-processing out of the engine.

- [ ] **Step 6: Wire `AppContainer` to use the streaming downloader when provider configuration is supplied; keep `MockDownloader` as deterministic default/dev behavior.**

- [ ] **Step 7: Run targeted/full tests; confirm GREEN.**

Run: `pytest tests/test_streaming_downloader.py -q && pytest -q`

- [ ] **Step 8: Commit.**

Commit message: `feat: add resumable streaming downloader`

---

### Task 6: Queue/downloader benchmarks and measurable gates

**Files:**
- Modify: `benchmarks/scenarios.py`
- Modify: `benchmarks/run_baseline.py`
- Test: `tests/test_benchmark_runner.py`
- Test: `tests/test_postgres_benchmarks.py`
- Create: `tests/test_downloader_benchmarks.py`

**Interfaces:**
- Produces scenarios:
  - `queue_deque_roundtrip`
  - `postgres_queue_claim_transition`
  - `streaming_downloader_memory`
  - `streaming_downloader_throughput`
  - `progress_coalescing`
- Retains legacy `queue_roundtrip` as PR1 comparison reference until PR5 performance record is merged.

- [ ] **Step 1: Write RED benchmark-contract tests** requiring all new scenarios in smoke/CI profiles at bounded scales, requiring a memory-growth assertion for fixed chunk/concurrency settings, and requiring persistence-write reduction in the coalescing scenario.

- [ ] **Step 2: Run benchmark tests and confirm RED.**

Run: `pytest tests/test_benchmark_runner.py tests/test_postgres_benchmarks.py tests/test_downloader_benchmarks.py -q`

- [ ] **Step 3: Implement `queue_deque_roundtrip`** using the new compatibility queue and the same logical enqueue/drain work as the legacy benchmark.

- [ ] **Step 4: Implement PostgreSQL claim/transition benchmark** with fixture setup excluded from measured samples; measure claim plus terminal transition, not synthetic row creation.

- [ ] **Step 5: Implement streaming throughput and memory scenarios** using deterministic in-process chunk providers with zero artificial delay; report CPU wall timing and `tracemalloc`/RSS diagnostics separately from bytes/sec.

- [ ] **Step 6: Add an optional delayed-provider diagnostic scenario** only if it does not make normal CI flaky; label it network/provider-bound and do not use it as the application performance gate.

- [ ] **Step 7: Implement progress-coalescing benchmark** comparing raw progress event count to actual persistence writes and require a substantial reduction while retaining forced terminal flush.

- [ ] **Step 8: Run targeted/full benchmark profile and record results.**

Run: `python benchmarks/run_baseline.py --profile ci --output-dir benchmark-results/pr5`

- [ ] **Step 9: Add/adjust hard gates only from fresh measured evidence**; never weaken correctness or lower workload to pass.

- [ ] **Step 10: Run full tests; confirm GREEN and commit.**

Commit message: `perf: benchmark queue and streaming downloader`

---

### Task 7: Performance record, regression review, exact-head CI, and PR

**Files:**
- Create: `docs/performance/optimization-pr5-queue-downloader-efficiency.md`
- Update: `docs/superpowers/plans/2026-09-03-optimization-pr5-queue-downloader-efficiency.md` checkboxes only if useful for final record.

**Interfaces:**
- Records queue before/after, PostgreSQL durable claim cost, downloader CPU/memory/throughput, progress-write reduction, fallback/concurrency correctness, and disk/database tradeoffs.

- [ ] **Step 1: Capture fresh exact implementation-head benchmark results** including the PR1 10K queue reference (~107 ms p95) and PR5 queue/downloader measurements.

- [ ] **Step 2: Document regression review** for CPU, Python/RSS memory, temporary disk I/O, PostgreSQL write volume, API isolation, provider/network separation, and recovery guarantees.

- [ ] **Step 3: Review branch diff against PR5 scope** and remove any PR6+ importer/media, PR7 metadata, or PR8 frontend changes.

- [ ] **Step 4: Open a draft PR** titled `Optimization PR 5: queue and downloader efficiency`, base `main`, head `feature/optimization-pr5-queue-downloader-efficiency`.

- [ ] **Step 5: Run fresh exact-head GitHub Actions** and require migrations/backend tests, frontend build, benchmark gate, benchmark summary, and artifact upload to succeed.

- [ ] **Step 6: Review all PR threads/comments and fix Critical/Important findings before merge.**

- [ ] **Step 7: Re-run exact-head CI after the last code/doc change.**

- [ ] **Step 8: Mark ready and merge only the exact verified head.**

- [ ] **Step 9: Verify `main` contains the merge commit and PR5 remains isolated from PR6.**
