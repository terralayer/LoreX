# LoreX Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the smallest end-to-end LoreX slice proving mocked NNTP headers can become an indexed audiobook release, be searched/grabbed, downloaded from a deterministic mock payload, imported into a managed library record, and displayed through the light-mode LoreX UI shell.

**Architecture:** Use a Python/FastAPI modular monolith with focused indexer/downloader/library modules and an in-process repository abstraction for the first slice; PostgreSQL/Redis wiring is included in Docker Compose but persistence adapters remain behind interfaces so the mocked slice is deterministic. A React/TypeScript frontend consumes the API and establishes the approved ScarletX-derived light UI shell. GitHub Actions provides fresh pytest and frontend build evidence.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, React 18, TypeScript, Vite, PostgreSQL 16, Redis 7, Docker Compose

**Spec:** `docs/superpowers/specs/2026-09-01-lorex-v1-design.md`

## Global Constraints

- Single-user v1.
- Audiobook-only scope.
- Newznab Audio/Audiobook category is 3030.
- M4B is the preferred managed-library format.
- Do not retain raw Usenet headers long-term.
- Broad production backfill is blocked until the end-to-end mocked vertical slice passes.
- UI is light-mode ScarletX-inspired with the approved LoreX identity.
- No destructive duplicate deletion.

---

### Task 1: Backend bootstrap and health API

**Files:**
- Create: `pyproject.toml`
- Create: `backend/lorex/__init__.py`
- Create: `backend/lorex/main.py`
- Create: `tests/test_health.py`

**Interfaces:**
- Produces: `backend.lorex.main.app: FastAPI`
- Produces: `GET /api/health -> {"status":"ok","app":"LoreX"}`

- [ ] Write `tests/test_health.py` using `fastapi.testclient.TestClient` and assert `/api/health` returns status 200 and exact JSON.
- [ ] Run `pytest tests/test_health.py -v`; expected FAIL because package/app do not exist.
- [ ] Add Python project dependencies and minimal FastAPI app.
- [ ] Run `pytest tests/test_health.py -v`; expected PASS.
- [ ] Commit `feat: bootstrap LoreX API`.

### Task 2: Header grouping, audiobook classification, and NZB generation

**Files:**
- Create: `backend/lorex/domain.py`
- Create: `backend/lorex/indexer/grouping.py`
- Create: `backend/lorex/indexer/classifier.py`
- Create: `backend/lorex/indexer/nzb.py`
- Create: `tests/fixtures/mock_headers.json`
- Create: `tests/test_indexer.py`

**Interfaces:**
- Produces: `ArticleHeader`, `ReleaseCandidate`, `IndexedRelease`
- Produces: `group_headers(headers: list[ArticleHeader]) -> list[ReleaseCandidate]`
- Produces: `classify_audiobook(candidate: ReleaseCandidate) -> float`
- Produces: `build_nzb(candidate: ReleaseCandidate) -> str`

- [ ] Add fixture containing a three-part M4B audiobook plus one obvious non-audiobook article.
- [ ] Write failing tests requiring the three audiobook parts to group into one candidate, score >= 0.8, and produce valid NZB XML containing all message IDs.
- [ ] Run `pytest tests/test_indexer.py -v`; expected FAIL.
- [ ] Implement minimal deterministic grouping by normalized subject stem, scoring by audiobook extensions/keywords and negative indicators, and XML generation.
- [ ] Run `pytest tests/test_indexer.py -v`; expected PASS.
- [ ] Commit `feat: index audiobook release fixtures`.

### Task 3: Release repository and search/grab API

**Files:**
- Create: `backend/lorex/repository.py`
- Create: `backend/lorex/services/indexing.py`
- Create: `backend/lorex/api/releases.py`
- Modify: `backend/lorex/main.py`
- Create: `tests/test_release_api.py`

**Interfaces:**
- Produces: `ReleaseRepository.add(release)`, `.search(query)`, `.get(release_id)`
- Produces: `POST /api/index/mock`
- Produces: `GET /api/releases/search?q=`
- Produces: `POST /api/releases/{release_id}/grab`

- [ ] Write API test that posts the fixture headers, searches `Project Hail Mary`, receives exactly one audiobook release, then grabs it and receives a queued job id.
- [ ] Run `pytest tests/test_release_api.py -v`; expected FAIL.
- [ ] Implement repository/service/router with application-lifetime in-memory storage for deterministic milestone behavior.
- [ ] Run `pytest tests/test_release_api.py -v`; expected PASS.
- [ ] Commit `feat: expose indexed release search and grab`.

### Task 4: Mock downloader and library importer

**Files:**
- Create: `backend/lorex/downloader/mock.py`
- Create: `backend/lorex/library/importer.py`
- Create: `backend/lorex/api/library.py`
- Modify: `backend/lorex/api/releases.py`
- Modify: `backend/lorex/main.py`
- Create: `tests/test_download_import.py`

**Interfaces:**
- Produces: `MockDownloader.download(release) -> DownloadResult`
- Produces: `LibraryImporter.import_download(result) -> LibraryBook`
- Produces: `GET /api/library/books`

- [ ] Write failing test that grabs the indexed fixture, processes the queued mock job, and asserts a `Project Hail Mary.m4b` library record exists under `/library/Andy Weir/Project Hail Mary/Project Hail Mary.m4b`.
- [ ] Run `pytest tests/test_download_import.py -v`; expected FAIL.
- [ ] Implement deterministic mock download result and importer that sanitizes author/title and creates a library record without touching copyrighted external content.
- [ ] Run `pytest tests/test_download_import.py -v`; expected PASS.
- [ ] Commit `feat: prove download to library vertical slice`.

### Task 5: Light-mode LoreX frontend shell

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `/api/health`, `/api/releases/search`, `/api/library/books`
- Produces: responsive LoreX dashboard shell with sidebar navigation and summary/release/download/library panels.

- [ ] Add the Vite React TypeScript project.
- [ ] Implement approved light-mode shell: white/light-neutral surfaces, purple accents, sidebar, top search, compact cards/tables, and LoreX wordmark treatment.
- [ ] Use deterministic sample-state fallback when API data is unavailable during static build; no fake network mutation.
- [ ] Run `npm --prefix frontend install` then `npm --prefix frontend run build`; expected PASS.
- [ ] Commit `feat: add LoreX light dashboard shell`.

### Task 6: Docker and CI verification

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.gitignore`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: API service on port 8000, frontend dev/build container path, PostgreSQL 16, Redis 7.
- Produces: CI jobs `backend` and `frontend`.

- [ ] Add Dockerfile and Compose services for `api`, `postgres`, and `redis`, with durable placeholder mounts for `/config`, `/downloads`, `/library`.
- [ ] Add CI installing Python dependencies and running `pytest -q`, plus Node 20 installing frontend dependencies and running `npm run build`.
- [ ] Push branch and inspect GitHub Actions results.
- [ ] If any job fails, inspect logs, patch the smallest failing unit, and rerun until green.
- [ ] Commit `ci: verify LoreX vertical slice`.

## Acceptance

The milestone is complete only when fresh CI evidence shows backend tests and frontend build pass, and the mocked flow proves:

`headers -> grouped audiobook -> NZB -> search -> grab -> mock download -> import -> library`
