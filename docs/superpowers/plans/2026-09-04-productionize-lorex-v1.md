# LoreX Productionization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LoreX 0.1.1 alpha a usable browser-driven audiobook Usenet app with real provider configuration, continuous scanning, automatic downloads, physical library imports, and zero fabricated operational UI data.

**Architecture:** Preserve the existing PostgreSQL/NNTP/downloader foundations and add durable orchestration state plus long-running scanner/download workers. The React UI becomes an API-backed control plane for only implemented features. Production mock behavior is opt-in and disabled by default.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL 16, Redis 7, React/TypeScript/Vite, Docker Compose, existing synchronous TLS NNTP client/yEnc decoder, 7z/par2 for post-processing.

**Spec:** `docs/superpowers/specs/2026-09-04-productionize-lorex-v1-design.md`

## Global Constraints
- Keep product version `0.1.1 alpha`, Python `0.1.1a1`, npm `0.1.1-alpha.1`.
- No plaintext provider secrets in API responses, logs, tests, docs, or commits.
- No default production mock release/downloader path.
- Existing search/read performance gates remain required.
- The final user-visible workflow must require no manual `/downloads/process-next` call.

---

### Task 1: Production mock boundary and honest navigation

**Files:**
- Modify: `backend/lorex/api/releases.py`
- Modify: `backend/lorex/main.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/routes/HomePage.tsx`
- Test: `tests/test_production_mock_boundary.py`

**Interfaces:**
- Consumes: `LOREX_ENABLE_MOCK_API` environment variable.
- Produces: `AppContainer.mock_api_enabled: bool`; `/api/index/mock` returns 404 in default production mode.

- [ ] Write failing backend tests that build the app with no `LOREX_ENABLE_MOCK_API`, call `/api/index/mock`, and expect 404; with `LOREX_ENABLE_MOCK_API=1`, expect existing mock behavior.
- [ ] Run the focused test and capture RED.
- [ ] Add the environment-gated mock boundary and remove implicit production mock handling.
- [ ] Remove disabled placeholder navigation entries for Wanted/Authors/Series/Narrators and all hard-coded operational counts from App/Home; retain only real API-backed counters or explicit empty/configuration states.
- [ ] Run focused backend tests and `npm run build`.
- [ ] Commit.

### Task 2: Provider Settings UI

**Files:**
- Create: `frontend/src/routes/SettingsPage.tsx`
- Create: `frontend/src/components/ProviderEditor.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/data/api.ts`
- Test: `frontend/src/routes/SettingsPage.test.tsx` if frontend test harness is present; otherwise add API contract tests in `tests/test_nntp_settings_api.py` and require TypeScript build.

**Interfaces:**
- Consumes existing masked provider APIs under `/api/settings/nntp/providers`.
- Produces browser create/edit/delete/test/clear operations; empty secret values on edit are omitted so stored secrets remain unchanged.

- [ ] Add failing contract tests for unchanged secret semantics and safe test-connection errors where coverage is missing.
- [ ] Run RED.
- [ ] Add a reusable JSON mutation helper to `frontend/src/data/api.ts` that surfaces sanitized API detail errors.
- [ ] Build Settings page provider cards/table and add/edit form for name, host, port, username, password, enabled, priority, fill-server, max connections, and groups.
- [ ] Add Test Connection, explicit clear username/password, and delete actions.
- [ ] Wire `/settings` navigation.
- [ ] Verify backend tests and frontend production build.
- [ ] Commit.

### Task 3: Durable scanner state and continuous worker

**Files:**
- Create: `migrations/versions/0007_runtime_orchestration.py`
- Modify: `backend/lorex/db_models.py`
- Create: `backend/lorex/runtime_repository.py`
- Modify: `backend/lorex/workers/nntp_scanner.py`
- Create: `backend/lorex/api/indexer.py`
- Modify: `backend/lorex/main.py`
- Modify: `docker-compose.yml`
- Test: `tests/test_scanner_runtime.py`
- Test: `tests/test_indexer_api.py`

**Interfaces:**
- Produces `ScannerGroupStateRow(provider_id, group_name, status, last_started_at, last_completed_at, last_error, last_scanned_count, last_indexed_count)`.
- Produces `RuntimeSettingRow(key, value)` with `scan_interval_seconds` and `scanner_enabled`.
- Produces `GET /api/indexer/status`, `PATCH /api/indexer/settings`, `POST /api/indexer/scan-now`.
- Worker CLI supports `--once` for tests/admin and continuous default operation with bounded sleep.

- [ ] Write migration/model/repository tests first and verify RED.
- [ ] Implement migration and repository with atomic state updates.
- [ ] Write worker tests proving one failing group does not terminate processing of later groups and continuous mode respects enabled/interval/manual-scan state.
- [ ] Implement continuous scanner loop using existing `scan_provider_group_once`; record start/success/error without logging credentials.
- [ ] Add indexer API and register router.
- [ ] Change Compose scanner service from one-shot/restart-no to continuous/restart-unless-stopped.
- [ ] Run migration + focused tests + full backend tests.
- [ ] Commit.

### Task 4: Real Downloads API and automatic worker

**Files:**
- Modify: `backend/lorex/db_models.py`
- Extend: `migrations/versions/0007_runtime_orchestration.py` with download job error/cancel fields, or create `0008_download_runtime.py` if 0007 has already shipped.
- Modify: `backend/lorex/postgres_repository.py`
- Create: `backend/lorex/services/download_jobs.py`
- Create: `backend/lorex/workers/download_worker.py`
- Create: `backend/lorex/api/downloads.py`
- Modify: `backend/lorex/api/releases.py`
- Modify: `backend/lorex/main.py`
- Modify: `docker-compose.yml`
- Test: `tests/test_download_worker.py`
- Test: `tests/test_downloads_api.py`

**Interfaces:**
- Produces idempotent `queue_release(release_id) -> DownloadJob`.
- Produces `process_next_download(container, worker_id) -> DownloadProcessResult | None`, used by both worker and compatibility endpoint.
- Produces `GET /api/downloads`, `POST /api/downloads/{id}/retry`, `POST /api/downloads/{id}/cancel`.

- [ ] Write failing tests for duplicate Grab, FIFO claim, automatic service processing, failure persistence, retry, and cancellation.
- [ ] Implement repository operations and service boundary; make release Grab call queue service.
- [ ] Move current `/downloads/process-next` implementation into `services/download_jobs.py` so API and worker share one path.
- [ ] Implement continuous worker with idle sleep, graceful SIGTERM handling, and no crash-loop on a single failed job.
- [ ] Add Downloads API and router.
- [ ] Add Compose `download-worker` service with same database/key/download/library mounts and restart-unless-stopped.
- [ ] Run focused and full backend tests.
- [ ] Commit.

### Task 5: Physical post-processing and atomic library import

**Files:**
- Modify: `backend/lorex/domain.py`
- Modify: `backend/lorex/downloader/engine.py`
- Create: `backend/lorex/postprocess.py`
- Modify: `backend/lorex/library/importer.py`
- Modify: `backend/lorex/services/download_jobs.py`
- Modify: `Dockerfile`
- Test: `tests/test_postprocess.py`
- Test: `tests/test_library_importer_files.py`
- Test: `tests/test_downloader_output_order.py`
- Test: `tests/test_docker_postprocess_tools.py`

**Interfaces:**
- Extend `DownloadResult` with `staging_dir: str` and ordered `article_paths: tuple[str, ...]` while preserving existing metadata fields.
- Produce `PostProcessor.process(result: DownloadResult) -> ProcessedAudiobook(path: Path, format: str, size: int)`.
- Produce `LibraryImporter.import_file(release_metadata, processed_path) -> LibraryBook`; it atomically moves/copies the actual file then commits the DB row.

- [ ] Write RED tests proving downloaded article outputs preserve release article order and importer refuses nonexistent source files.
- [ ] Change downloader to collect ordered complete paths while preserving concurrent network transfer.
- [ ] Add postprocessor tests for direct audio, split direct payload concatenation, archive extraction, PAR2 invocation when present, and no-audio failure.
- [ ] Implement postprocessor using subprocess argument arrays (never shell=True), bounded paths under the job staging directory, `7z`, and `par2`.
- [ ] Implement physical atomic library placement before repository insertion; ensure a DB failure does not silently claim an absent file.
- [ ] Package post-processing binaries in Docker and add packaging tests.
- [ ] Update download service to run postprocessor then physical importer.
- [ ] Run focused/full tests.
- [ ] Commit.

### Task 6: Live Downloads, Indexer, Activity, and Search controls in React

**Files:**
- Create: `frontend/src/routes/DownloadsPage.tsx`
- Create: `frontend/src/routes/IndexerPage.tsx`
- Create: `frontend/src/routes/ActivityPage.tsx`
- Modify: `frontend/src/routes/SearchPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/responsive.css`

**Interfaces:**
- Search Grab calls `POST /api/releases/{id}/grab` and refreshes release status.
- Downloads consumes `GET /api/downloads` and mutation endpoints.
- Indexer consumes `/api/indexer/*`.
- Activity consumes `/api/activity` from Task 7.

- [ ] Add backend contract tests first for response shapes consumed by frontend if not already present.
- [ ] Add Grab/status controls to Search without optimistic fake progress.
- [ ] Add Downloads route with queued/active/completed/failed sections, real progress, error, retry/cancel.
- [ ] Add Indexer route with scanner enabled/interval, Scan Now, provider/group state/checkpoint/error.
- [ ] Add Activity route consuming real events.
- [ ] Enable only implemented nav links.
- [ ] Run TypeScript production build and backend API tests.
- [ ] Commit.

### Task 7: Live system summary, activity, provider health, and honest Home

**Files:**
- Create: `backend/lorex/api/system.py`
- Extend: `backend/lorex/runtime_repository.py`
- Modify: `backend/lorex/main.py`
- Rewrite: `frontend/src/routes/HomePage.tsx`
- Test: `tests/test_system_api.py`

**Interfaces:**
- Produces `GET /api/system/summary` with library/release/download counts, scanner state, recent releases/jobs, provider-health snapshots, and configuration readiness.
- Produces `GET /api/activity?limit=N` from durable scanner/download/import transitions ordered newest-first.

- [ ] Write RED tests on an empty database proving zero/needs-configuration output, not sample data.
- [ ] Add real summary queries using bounded indexed queries/counts.
- [ ] Add durable activity event writes from scanner/download/import services and read API.
- [ ] Rewrite Home to render only returned data, with zero-state onboarding pointing to Settings when no provider exists.
- [ ] Add provider health calculations from `ProviderHealthRow` attempts/success/bytes/elapsed time; never invent speed before measured bytes/time exist.
- [ ] Run focused tests, full backend tests, frontend build, and performance benchmark.
- [ ] Commit.

### Task 8: Full deterministic production E2E and deployment validation

**Files:**
- Create: `tests/test_production_flow_e2e.py`
- Modify: `tests/support/fake_nntp.py` only if fixture features are required.
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `docker-compose.yml` as required by verified test findings.

**Interfaces:**
- End-to-end path: encrypted provider -> provider test -> scanner -> release search -> grab -> download worker -> fake TLS BODY primary/fill -> post-process -> physical library file -> library API/system summary.

- [ ] Write end-to-end test against PostgreSQL and fake TLS servers using a tiny synthetic non-copyrighted audio-shaped payload/fixture.
- [ ] Verify no mock API is enabled and no real provider credentials are present.
- [ ] Run test RED and fix only root causes discovered in production path.
- [ ] Add CI gate for full production E2E and Docker build/config validation.
- [ ] Update README with fresh-install browser workflow and worker roles.
- [ ] Run complete backend test suite, frontend production build, migrations from empty DB, benchmark gates, Docker build, and deterministic E2E.
- [ ] Open PR from `feature/productionize-lorex-v1` to `main`; require exact-head CI green before merge.
