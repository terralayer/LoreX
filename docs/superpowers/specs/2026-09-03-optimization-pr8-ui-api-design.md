# LoreX Optimization PR 8 — UI and API Responsiveness Design

## Status

This is the eighth and final stage of the locked LoreX `0.1.1 alpha` whole-app optimization program. PR 8 begins only after PR 7 is merged and does not change the product version.

## Problems verified on the PR 7 baseline

1. The Home screen calls `/api/library/books` and downloads the complete library merely to display a count.
2. `/api/library/books` has no pagination contract and serializes every library record.
3. The top-level React application is one monolithic eagerly loaded component.
4. The visible search control is not an input and does not call the indexed release-search API.
5. Navigation buttons do not load real views.
6. There is no client request cache or in-flight request coalescing, so future page growth would make redundant reads easy to introduce.
7. There is no debounced search contract.
8. `body { min-width: 1100px }` prevents the approved UI from being responsive on tablets and phones.
9. The sidebar still renders a placeholder text/unicode logo structure even though the approved LoreX SVG already ships in `public/`.
10. Frontend production builds are checked, but frontend behavior has no executable test gate.

## Architecture

### Lightweight library reads

`GET /api/library/books` becomes a bounded page endpoint:

- default `limit=50`
- hard maximum `limit=100`
- non-negative `offset`
- response fields: `total`, `count`, `limit`, `offset`, `books`
- deterministic ordering by author, title, then id

Both in-memory and PostgreSQL library repositories expose `count()` and `page(limit, offset)` while retaining `all()` for compatibility. PostgreSQL gets a composite `(author, title, id)` index so normal library paging does not require a full sort at scale.

### Dashboard aggregation

`GET /api/library/dashboard` remains the single dashboard aggregate read and gains `total_books`. Home must consume this aggregate rather than the complete library collection. Release/download/import status aggregates continue to come from the optimized repository query introduced earlier.

### Bounded frontend collections

Search and Library views render at most 50 rows per page and page on the server. Because the visible collection is hard-bounded at 50, PR 8 intentionally does not add a virtualization dependency. Virtualization becomes appropriate only if a future view deliberately renders hundreds of simultaneous rows.

### Search

The header search becomes a real form. Search results use `/api/releases/search` with server-side pagination and the existing PostgreSQL indexed search path. Query changes are debounced by 250 ms; explicit form submission navigates immediately.

### Client request cache

A tiny application-local query client provides:

- TTL caching for stable GET results
- one in-flight Promise per cache key
- invalidation by exact key or prefix
- no persisted user or provider secrets

This prevents duplicate panel/page reads without adding a large state-management dependency.

### Polling

Home refreshes the single dashboard snapshot on a modest interval only while the document is visible. The query client coalesces overlapping reads. PR 8 does not introduce per-panel polling.

### Code splitting

Home, Search, Library, and placeholder views are loaded with `React.lazy`/`Suspense`. The shell, navigation, and header remain in the initial chunk. Vite emits a manifest so the benchmark can distinguish the initial entry bundle from dynamic page chunks.

### Responsive shell

The fixed 1100px body minimum is removed. The sidebar becomes an off-canvas drawer at mobile widths, metrics collapse from five columns to two and then one, dashboard panels become single-column, and list/table containers remain horizontally safe. Desktop keeps the approved light ARR-style layout.

### Branding

The shell uses `/lorex-logo.svg` directly. No TerraLayer branding is added to LoreX.

## Verification and performance gates

PR 8 must preserve all prior gates and add:

- frontend unit tests for request coalescing/TTL and debounce behavior
- library page limit never exceeds 100
- representative PostgreSQL library-page API p95 `<100 ms`
- dashboard aggregate API p95 `<250 ms`
- at least three dynamic frontend page chunks in the Vite manifest
- initial entry JavaScript gzip bytes below the prior single-bundle frontend JavaScript baseline
- production frontend build succeeds at the exact PR head
- whole-app, PR 6, and PR 7 benchmark regressions remain green

Hosted-runner timing is interpreted with the same variance caveat as prior PRs. Hard PR-8 gates use workloads directly controlled by this PR.
