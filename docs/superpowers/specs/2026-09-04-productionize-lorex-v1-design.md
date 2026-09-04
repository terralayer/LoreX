# LoreX Productionization Design

## Goal
Turn the deployed LoreX 0.1.1 alpha application from a demo-oriented shell into a working self-hosted audiobook Usenet application whose visible state is derived from PostgreSQL/runtime state and whose primary workflow is usable from the browser: configure provider, test provider, scan, search, grab, download, import, and inspect library/activity.

## Locked constraints
- Product version stays `0.1.1 alpha` / Python `0.1.1a1` / npm `0.1.1-alpha.1`.
- Preserve the approved light ScarletX-inspired compact ARR-style UI and LoreX branding.
- PostgreSQL remains the durable system of record.
- Redis may be used for coordination but must not be the only copy of user-visible durable state.
- Production provider credentials remain AES-256-GCM encrypted using `LOREX_CREDENTIAL_KEY`; plaintext credentials are never returned by APIs or logged.
- Production mode must never silently fall back to mock data or the mock downloader.
- Existing NNTP TLS verification, provider/fill fallback, yEnc decoding, query-performance gates, and current API compatibility are preserved unless explicitly replaced below.

## Current failures being corrected
1. `HomePage.tsx` hardcodes recent releases, wanted entries, download progress/speeds, indexer state, provider health, and activity.
2. Navigation advertises Wanted, Downloads, Authors, Series, Narrators, Indexer, Activity, and Settings without working routes.
3. The scanner worker accepts only `--once`, so scanning does not continue in production.
4. `POST /api/releases/{id}/grab` only queues a job; a manual `POST /api/downloads/process-next` is required to make progress.
5. The current downloader stores per-article decoded files but there is no complete production orchestration worker around download/post-processing/import.
6. `LibraryImporter` currently persists a destination path but does not itself prove that a final audiobook file exists at that path.
7. There is no durable scanner run/status model for last run, current group, counters, or last error.

## Architecture

### 1. Real application state
All operational panels consume API responses backed by PostgreSQL/runtime workers. Static operational arrays and fake counters are removed. Empty systems display empty/needs-configuration states rather than invented releases, providers, speeds, Wanted counts, or activity.

### 2. Provider settings
The browser exposes a working Settings > Usenet Providers page backed by the existing masked NNTP settings API. Create/edit/delete, enable/disable, primary/fill priority, TLS port, connection count, group configuration, explicit credential clear, and Test Connection are supported. On edit, an empty credential input means keep the stored secret.

### 3. Continuous scanning
The scanner becomes a long-running worker. It loops enabled provider/group pairs at a configurable interval, records run state, and supports an explicit Scan Now request. A failure in one provider/group is recorded and does not terminate the worker. Existing checkpoints remain the authority for live scan progress.

A new durable scanner-state table stores per provider/group: status (`idle|scanning|error`), last_started_at, last_completed_at, last_error, last_scanned_count, and last_indexed_count. A small global control row stores `scan_interval_seconds` and a monotonic/manual-scan request token.

### 4. Download queue worker
Grab remains idempotent for an already-active release and queues a durable `DownloadJobRow`. A long-running download worker claims queued jobs in FIFO order, builds the live NNTP downloader, downloads persisted release articles, records progress/provider health, post-processes the staged result, imports it, and marks the job completed or failed with a durable error.

The existing manual process-next endpoint remains for tests/admin compatibility but calls the same service used by the worker.

### 5. Post-processing and real library files
Post-processing has a strict first production slice:
- decoded article files are tracked in release article order rather than hash order only;
- direct single-file and split-file audiobook payloads are assembled into a staging file;
- supported archive sets are extracted with `7z`; PAR2 verification/repair uses `par2` when PAR2 files exist;
- the final import accepts actual `.m4b`, `.m4a`, `.mp3`, `.aac`, or `.flac` files;
- the final file is moved atomically into `/library/<author>/<title>/...` before the library row is committed;
- import fails closed if no supported audio file is produced.

Container packaging installs the required non-interactive post-processing binaries and validates their presence in CI.

### 6. APIs
Add production APIs:
- `GET /api/system/summary` — live dashboard/system counters.
- `GET /api/activity` — recent durable job/scanner/import/provider events.
- `GET /api/downloads` — queued/active/completed/failed jobs with byte/article progress and release summary.
- `POST /api/downloads/{job_id}/retry` and `POST /api/downloads/{job_id}/cancel` where state allows.
- `GET /api/indexer/status` — scanner controls plus provider/group status/checkpoints.
- `PATCH /api/indexer/settings` — scan interval and enabled state.
- `POST /api/indexer/scan-now` — request an immediate pass.

Existing `GET /api/releases/search`, release detail/NZB/grab, library APIs, and masked NNTP provider APIs stay available.

### 7. Browser routes
Enable real routes only:
- Home
- Search
- Downloads
- Library
- Indexer
- Activity
- Settings

Wanted, Authors, Series, and Narrators are removed from navigation until backed by real domain/state rather than placeholders.

Search results get a real Grab button and status. Downloads shows real queue/progress/errors/retry/cancel. Indexer shows configured providers/groups, checkpoints, last run, errors, and Scan Now. Settings exposes provider CRUD/test. Home uses live summary plus recent real releases/jobs/activity/provider health.

### 8. Production mock boundary
`/api/index/mock` and `MockDownloader` remain available only when `LOREX_ENABLE_MOCK_API=1`. The default Docker/TrueNAS deployment does not set it, so production cannot create fake releases or silently process them.

### 9. Deployment
Docker Compose starts PostgreSQL and Redis, runs migrations automatically, then runs three application roles from the same image:
- `api`
- `nntp-scanner`
- `download-worker`

Both workers restart unless stopped. Persistent host/container paths remain `/config`, `/downloads`, and `/library` from the application perspective.

## Success criteria
A clean NAS deployment with a valid `LOREX_CREDENTIAL_KEY` can be used entirely from the browser to:
1. add Astraweb (or another compatible provider) without exposing stored credentials;
2. test TLS/auth/group access;
3. trigger scanning and observe real checkpoint/status changes;
4. find releases populated by NNTP overview data;
5. click Grab and see a durable job advance automatically without a manual process-next request;
6. see live byte/article/provider progress;
7. produce a real supported audiobook file under `/library` and a matching PostgreSQL library row when the Usenet payload is supported;
8. show empty/error/configuration states rather than fabricated dashboard values;
9. restart containers without losing provider, scanner, queue, release, import, or library state.

## Verification
- TDD for each new service/API/UI behavior.
- Existing backend/frontend/performance CI remains green.
- Add deterministic fake TLS NNTP end-to-end test covering provider config -> scan -> search -> grab -> worker -> physical staged/final file -> library row.
- Add production-mode tests proving mock endpoints are disabled by default and secrets never appear in API/log payloads.
- Add Docker packaging tests for migrations, worker commands, and post-processing binaries.
