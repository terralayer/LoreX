# Optimization PR 6 Importer and Media Pipeline Efficiency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a durable, recoverable, bounded importer/media pipeline with safe archive handling, preserve/remux-first media processing, verified final promotion, and measurement-backed resource efficiency.

**Architecture:** PostgreSQL owns import-job lifecycle and oldest-first claims. A staged pipeline coordinates repair, extraction, probing, media processing, verification, promotion, and cleanup through small focused modules, while independent bounded gates isolate CPU-heavy work from downloader/API/indexer work.

**Tech Stack:** Python 3.12, SQLAlchemy 2, PostgreSQL 16, Alembic, subprocess-based PAR2/FFprobe/FFmpeg adapters, pathlib/shutil/os filesystem operations, pytest, existing LoreX benchmark harness.

**Spec:** `docs/superpowers/specs/2026-09-03-optimization-pr6-importer-media-pipeline-design.md`

## Global Constraints

- Product version remains `0.1.1 alpha`; Python `0.1.1a1`; npm `0.1.1-alpha.1`.
- PR 6 only; PR 7 metadata caching and PR 8 UI/API work are out of scope.
- PostgreSQL is authoritative durable state.
- Source cleanup occurs only after verified final-file success and library persistence.
- Archive traversal and extraction-size safeguards are mandatory.
- Valid M4B must not be re-encoded.
- CPU-heavy repair/extraction/FFmpeg work must have bounded independent concurrency.
- Oldest completed import work is processed first.
- Every behavior change follows red-green TDD and exact-head CI is required before merge.

---

### Task 1: Durable import-job queue and migration

**Files:**
- Modify: `backend/lorex/db_models.py`
- Modify: `backend/lorex/domain.py`
- Modify: `backend/lorex/postgres_repository.py`
- Create: `migrations/versions/0004_import_pipeline_efficiency.py`
- Create: `tests/test_import_job_queue.py`
- Create: `tests/test_postgres_import_queue.py`
- Modify: `tests/test_database_schema_pr5.py` only if the existing schema-chain test requires the new head.

**Interfaces:**
- Produces `ImportJob` dataclass with id, release_id, source_path, status, stage.
- Produces `PostgresImportJobRepository.add`, `claim_next(worker_id)`, `set_stage`, `mark_completed`, `mark_failed`, `recover_stale`.

- [ ] Write failing tests proving oldest-first claim, `FOR UPDATE SKIP LOCKED`, stage persistence, terminal state, and stale-claim recovery.
- [ ] Run targeted tests and confirm RED because the new domain/repository behavior does not exist.
- [ ] Add import-job columns/indexes including identity `created_order`, claim timestamps/worker, paths, stage, timestamps, error, and metrics.
- [ ] Implement repository methods with PostgreSQL transactions and oldest-first ordering.
- [ ] Run targeted tests to GREEN and commit `feat: add durable import job queue`.

### Task 2: Safe archive inspection and extraction budgets

**Files:**
- Create: `backend/lorex/library/archive.py`
- Create: `tests/test_archive_safety.py`

**Interfaces:**
- Produces `ArchiveLimits(max_files: int, max_extracted_bytes: int)`.
- Produces `validate_archive_members(members, limits) -> ArchiveManifest`.
- Produces `ArchiveSafetyError`.

- [ ] Write failing tests rejecting absolute paths, parent traversal, escaping symlinks, too many files, and expanded-size overflow while allowing safe nested audiobook paths.
- [ ] Run tests and confirm RED.
- [ ] Implement normalized path validation with no extraction side effects; sum sizes incrementally and fail before limits are exceeded.
- [ ] Run tests to GREEN and commit `feat: add archive extraction safeguards`.

### Task 3: Bounded external-tool adapters and media decisions

**Files:**
- Create: `backend/lorex/library/tools.py`
- Create: `backend/lorex/library/media.py`
- Create: `tests/test_media_tools.py`
- Create: `tests/test_media_decisions.py`

**Interfaces:**
- Produces `MediaWorkerLimits(repair=1, extraction=1, ffmpeg=1)` with positive validation.
- Produces `ToolRunner.run(command, gate) -> CompletedProcess` without shell execution.
- Produces `MediaProbe(container, audio_codec, valid, duration_seconds)`.
- Produces `MediaAction` values `preserve`, `remux`, `transcode` and `choose_media_action(probe)`.

- [ ] Write failing tests proving separate bounded gates, shell-free argument execution, invalid limit rejection, valid M4B preserve, compatible non-M4B remux, and unsupported codec transcode fallback.
- [ ] Run tests and confirm RED.
- [ ] Implement focused tool and media-policy modules.
- [ ] Run tests to GREEN and commit `feat: add bounded media tool execution`.

### Task 4: Recoverable staged media pipeline

**Files:**
- Create: `backend/lorex/library/pipeline.py`
- Modify: `backend/lorex/library/importer.py`
- Create: `tests/test_import_pipeline.py`
- Create: `tests/test_import_pipeline_recovery.py`

**Interfaces:**
- Produces `ImportPipeline.process(job: ImportJob, result: DownloadResult) -> LibraryBook`.
- Pipeline dependencies are injected adapters for verify, repair, extract, probe, process, tag, final verify, promote and cleanup to keep tests deterministic.

- [ ] Write failing happy-path test asserting exact stage order and that a valid M4B takes preserve path with no FFmpeg encode call.
- [ ] Write failing failure-path tests proving source cleanup is not called when verification, extraction, processing, final verification, promotion, or library persistence fails.
- [ ] Write failing resume test proving a persisted later stage can restart without repeating already-confirmed destructive work.
- [ ] Run targeted tests and confirm RED.
- [ ] Implement orchestration with durable `set_stage` calls before expensive work and terminal status only after library persistence.
- [ ] Run targeted tests to GREEN and commit `feat: add recoverable import media pipeline`.

### Task 5: Verified filesystem promotion and cleanup

**Files:**
- Create: `backend/lorex/library/filesystem.py`
- Create: `tests/test_import_filesystem.py`

**Interfaces:**
- Produces `promote_verified_file(source: Path, destination: Path, verifier) -> int`.
- Same-filesystem path uses atomic `os.replace`; cross-filesystem fallback copies to a destination temporary path, flushes/fsyncs, verifies, then atomically renames.

- [ ] Write failing tests for same-filesystem atomic promotion, EXDEV fallback, destination verification failure, and guarantee that source remains when verification fails.
- [ ] Run tests and confirm RED.
- [ ] Implement copy/replace logic without loading whole files into Python memory.
- [ ] Run tests to GREEN and commit `feat: add verified atomic library promotion`.

### Task 6: Oldest-first importer worker and service integration

**Files:**
- Create: `backend/lorex/services/importing.py`
- Modify: `backend/lorex/main.py` only for dependency/container wiring required by tests; do not add UI/API work.
- Create: `tests/test_import_worker.py`

**Interfaces:**
- Produces `run_import_once(repository, pipeline, worker_id) -> bool`, claiming exactly one oldest job and processing it.

- [ ] Write failing tests proving no work returns false, oldest work is claimed first, exceptions become durable failed state, and worker does not spawn unbounded tasks.
- [ ] Run tests and confirm RED.
- [ ] Implement one-job worker orchestration around the durable queue and pipeline.
- [ ] Run tests to GREEN and commit `feat: add bounded import worker`.

### Task 7: PR6 benchmark coverage and regression evidence

**Files:**
- Modify: `benchmarks/scenarios.py`
- Modify: `benchmarks/run_baseline.py`
- Create: `tests/test_importer_benchmarks_pr6.py`
- Create: `docs/performance/optimization-pr6-importer-media-pipeline.md`

**Interfaces:**
- Adds deterministic scenarios for importer pipeline wall time, CPU time, temporary disk usage, bytes copied, action counts, and oldest-first queue claims.

- [ ] Write failing benchmark-contract tests asserting the new scenario names/metrics are published and bounded fixture sizes are used.
- [ ] Run tests and confirm RED.
- [ ] Implement deterministic no-network/no-real-encoding fixtures that distinguish Python/disk orchestration overhead from external tool latency.
- [ ] Run targeted benchmark tests to GREEN.
- [ ] Run fresh PR6 benchmark and record before/after/context numbers plus CPU/memory/disk regression review in the performance document.
- [ ] Commit `perf: benchmark PR6 importer media pipeline`.

### Task 8: Full verification, review, and pull request

**Files:**
- All PR6 files above.

- [ ] Run the full backend pytest suite against PostgreSQL with migrations at head.
- [ ] Run the frontend production build to prove no unrelated regression.
- [ ] Run the CI benchmark profile and inspect importer/media metrics.
- [ ] Review the branch against every PR6 requirement: verification/PAR2, extraction safety, M4B preserve/remux-first behavior, bounded heavy-tool concurrency, source-cleanup ordering, oldest-first processing, wall/CPU/temp-disk benchmark evidence.
- [ ] Open PR `Optimization PR 6: importer and media pipeline efficiency` against `main`, explicitly excluding PR7/PR8.
- [ ] Resolve all Critical/Important review findings with new regression tests.
- [ ] Require fresh CI on the exact final head; only then mark ready and merge with expected-head SHA protection.
