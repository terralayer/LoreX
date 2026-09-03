# LoreX Optimization PR 8 — UI/API Responsiveness Implementation Plan

> Execute this plan on `feature/optimization-pr8-ui-api`. Keep `0.1.1 alpha` unchanged.

## Task 1 — Lock backend read contracts with failing tests

Add API tests proving:

- `/api/library/books` defaults to a bounded page
- caller-supplied `limit`/`offset` are honored
- `limit > 100` is rejected
- the response includes both page `count` and full `total`
- `/api/library/dashboard` includes `total_books`

Run CI and require the failures to reflect the missing pagination/aggregate behavior before production changes.

## Task 2 — Implement bounded library repository/API reads

- add `count()` and `page()` to in-memory and PostgreSQL library repositories
- retain `all()` for compatibility
- add `(author, title, id)` PostgreSQL index and Alembic migration `0005_library_read_efficiency`
- update `/api/library/books` to use `page()` and `count()` only
- add `total_books` to dashboard response
- verify old download/import API compatibility tests remain green

## Task 3 — Add frontend behavior tests and utilities

- add Vitest as a development-only dependency
- add CI `npm test` gate
- write RED tests for `QueryClient` TTL/in-flight coalescing and debounce
- implement the small query client and debounce utility
- keep cache process-local and non-persistent

## Task 4 — Split the React application into bounded pages

- keep shell/header/sidebar in `App.tsx`
- lazy-load Home, Search, Library, and Placeholder pages
- wire navigation state
- convert header search to an accessible form/input
- Search page: 250 ms debounced indexed API reads, 50-row server pages
- Library page: 50-row server pages
- Home page: health + single `/api/library/dashboard` aggregate read; no full-library fetch
- poll only the aggregate dashboard while the page is visible
- use query cache/in-flight coalescing for GETs

## Task 5 — Make the approved UI responsive and use the real logo

- remove `min-width:1100px`
- desktop sidebar unchanged visually
- tablet/mobile sidebar drawer
- responsive metrics and dashboard columns
- safe list/table overflow
- use `/lorex-logo.svg` directly
- preserve light mode, purple accents, dense ARR-style presentation

## Task 6 — Add PR-8 benchmark gates

Backend benchmark with PostgreSQL fixture data:

- 100K library rows seeded outside measured sections
- `/api/library/books?limit=50&offset=50000` p95 `<100 ms`
- `/api/library/dashboard` p95 `<250 ms`
- returned library page size exactly 50

Frontend build benchmark:

- enable Vite manifest
- collect initial entry JavaScript raw/gzip size
- count dynamic page chunks
- require at least three dynamic chunks
- require initial entry gzip below the pre-split single-JS baseline

Wire `python -m benchmarks.run_pr8` into the existing benchmark job after PR 7 and publish `pr8-ui-api.md` in the artifact/summary.

## Task 7 — Regression review and final-head verification

Compare the exact final head against:

- streaming indexer target >=25K headers/sec at 100K
- PostgreSQL 1M release search <150 ms p95
- downloader/importer prior gates
- PR 7 metadata cache/coalescing gates
- frontend production build and frontend unit tests
- new PR 8 API/chunk gates

Record exact workflow run, artifact ID/digest, PR-8 measurements, and hosted-runner caveats in `docs/performance/optimization-pr8-ui-api.md`.

Open the non-draft PR, squash merge only after exact-head verification, then verify the merged `main` state. This completes the locked eight-PR optimization program.
