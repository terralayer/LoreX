# LoreX Optimization PR 8 UI/API Responsiveness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the eighth and final locked LoreX whole-app optimization stage by removing oversized dashboard/library reads, adding responsive paginated views, reducing redundant client traffic, and proving API/startup improvements with deterministic benchmarks.

**Architecture:** Keep PostgreSQL authoritative and extend the existing repository interfaces with lightweight library pagination/counts and dashboard aggregates. Split the React shell from lazy-loaded route pages, use a tiny request cache with in-flight coalescing and TTLs, debounce search before server requests, and window large visible lists. Add PR-8-specific benchmark gates for dashboard/read API latency and initial frontend entry-chunk size while retaining the existing full optimization benchmark suite.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/PostgreSQL 16, React 18, TypeScript, Vite 6, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-01-whole-app-optimization-design.md`

## Global Constraints

- Product/UI version remains `0.1.1 alpha`; Python `0.1.1a1`; npm `0.1.1-alpha.1`.
- Search API p95 remains `<150 ms` at 1,000,000 indexed releases.
- Normal read API p95 target is `<100 ms`.
- Dashboard aggregate API p95 target is `<250 ms`.
- PostgreSQL remains authoritative; Redis/cache state must not become durable truth.
- UI must not fetch a full catalog merely to render counts or a first page.
- Large logical result sets use server pagination and bounded/windowed rendering.
- Correctness behavior and responsive desktop/tablet/mobile layout must be preserved.

---

### Task 1: Lightweight library pagination and dashboard aggregates

**Files:**
- Modify: `backend/lorex/search.py`
- Modify: `backend/lorex/repository.py`
- Modify: `backend/lorex/postgres_repository.py`
- Modify: `backend/lorex/api/library.py`
- Test: `tests/test_library_api.py`
- Test: `tests/test_postgres_library_api.py`

**Interfaces:**
- Produces `LibrarySearchQuery`, `LibrarySummary`, `LibraryPage`, and `AppDashboardSummary` dataclasses.
- Produces repository methods `library.search_page(query)`, `library.count()`, and aggregate reads that never materialize the complete library.
- Produces `GET /api/library/books?limit=&offset=&q=&sort=&order=` and `GET /api/dashboard`.

- [ ] Write failing API tests proving `/api/library/books` returns bounded pagination metadata and `/api/dashboard` returns counts without requiring `library.all()`.
- [ ] Run focused tests and confirm the new contract fails before implementation.
- [ ] Implement in-memory repository pagination/count behavior.
- [ ] Implement PostgreSQL count + projection queries using `COUNT`, `LIMIT`, and `OFFSET` rather than loading ORM rows for the full catalog.
- [ ] Implement the API response models and routes.
- [ ] Run focused and full backend correctness tests.

### Task 2: Frontend request cache, debounced search, and route splitting

**Files:**
- Create: `frontend/src/data/api.ts`
- Create: `frontend/src/hooks/useDebouncedValue.ts`
- Create: `frontend/src/hooks/useQuery.ts`
- Create: `frontend/src/routes/HomePage.tsx`
- Create: `frontend/src/routes/LibraryPage.tsx`
- Create: `frontend/src/routes/SearchPage.tsx`
- Create: `frontend/src/components/VirtualList.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- `apiQuery<T>(key, url, {ttlMs})` caches stable results and shares one in-flight fetch per key.
- `useQuery<T>()` exposes cached state and avoids duplicate concurrent calls.
- `useDebouncedValue(value, 250)` delays search requests until typing settles.
- Route pages are loaded through `React.lazy()` so dashboard/library/search code is split into separate chunks.
- `VirtualList` renders only a bounded visible window for large current pages.

- [ ] Split the existing dashboard markup into a lazy `HomePage` while keeping the approved light-mode shell and branding.
- [ ] Replace the dashboard's `/api/library/books` full payload with `/api/dashboard`.
- [ ] Add a paginated library route that requests at most 100 books per server page.
- [ ] Add a debounced search route backed by `/api/releases/search` and server pagination/filtering.
- [ ] Add bounded window rendering to library/search result lists.
- [ ] Add a single visibility-aware refresh path for dashboard data instead of independent/redundant polling.
- [ ] Preserve responsive desktop/tablet/mobile styles and build successfully with TypeScript/Vite.

### Task 3: Progress/query update coalescing

**Files:**
- Modify: `frontend/src/data/api.ts`
- Modify: `frontend/src/routes/HomePage.tsx`
- Test: `tests/test_dashboard_api.py`

**Interfaces:**
- Stable dashboard queries use a short TTL and in-flight coalescing.
- Refresh timers pause while the document is hidden and resume with one immediate refresh when visible.
- UI progress data is updated at a bounded cadence rather than per-event/per-component polling.

- [ ] Add backend/API contract tests for a single lightweight dashboard request shape.
- [ ] Implement one dashboard refresh loop with page-visibility suppression.
- [ ] Verify no component independently polls the same endpoint.

### Task 4: PR 8 deterministic performance gates

**Files:**
- Create: `benchmarks/ui_api.py`
- Create: `benchmarks/run_pr8.py`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_pr8_benchmarks.py`

**Interfaces:**
- `run_ui_api_benchmarks()` measures PostgreSQL dashboard aggregate p95, paged library API p95, and frontend entry-chunk bytes.
- `run_pr8.py` fails when dashboard p95 is `>=250 ms`, normal paged read p95 is `>=100 ms`, a bounded endpoint returns more than its requested page, or the entry JS gzip size does not improve versus the PR-1 `48.67 kB` initial-script baseline.

- [ ] Write failing benchmark contract tests for the report schema and gates.
- [ ] Implement deterministic PostgreSQL fixture population and API timing.
- [ ] Identify the initial JS script from `frontend/dist/index.html` and measure raw/deterministic gzip bytes independently of lazy chunks.
- [ ] Wire `python -m benchmarks.run_pr8 --output benchmark-results --frontend-dist frontend/dist` into CI, summary publication, and the existing artifact.
- [ ] Run fresh PR-8 benchmark evidence and inspect regressions across the existing baseline/PR6/PR7 suites.

### Task 5: Evidence, review, and exact-head verification

**Files:**
- Create: `docs/performance/optimization-pr8-ui-api-responsiveness.md`
- Modify: `README.md` only if the existing performance-document index requires it.

**Interfaces:**
- Permanent evidence records before/after API payload behavior, p50/p95 measurements, frontend entry-chunk size, full bundle size, and CPU/memory/database regression notes.

- [ ] Record exact benchmark run, commit SHA, API p50/p95, initial entry raw/gzip bytes, total frontend bytes, and relevant existing gates.
- [ ] Review the branch against every PR-8 requirement in the locked design and explicitly note any non-applicable item.
- [ ] Run fresh exact-head CI and require backend, frontend, baseline benchmark, PR6, PR7, PR8, summary publication, and artifact upload to pass.
- [ ] Merge only after the exact head is verified.
