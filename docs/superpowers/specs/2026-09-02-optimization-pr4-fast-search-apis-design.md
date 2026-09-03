# Optimization PR 4: Fast Search and Lightweight Read APIs

## Status

Approved on 2026-09-02.

## Goal

Replace full-catalog release reads with indexed PostgreSQL queries that return bounded, lightweight pages. Preserve full release data for detail and NZB workflows, and verify a representative selective search remains below the locked 150 ms p95 budget at one million releases.

## Scope

PR 4 adds:

- trigram indexes for searchable text fields;
- an immutable repository search contract with bounded pagination, explicit filtering, and deterministic sorting;
- a lightweight release summary distinct from the full release domain object;
- a validated FastAPI search endpoint and a full-detail endpoint;
- aggregate dashboard reads that avoid N+1 queries;
- deterministic PostgreSQL benchmark scenarios at 100,000 and 1,000,000 releases.

Queue, downloader, importer, metadata, and frontend optimization work remains out of scope.

## Repository and Database Design

`PostgresReleaseRepository.search_page()` accepts a validated search query object and returns a page containing `total`, `limit`, `offset`, and release summaries. It performs one filtered count and one bounded summary-column query. It never loads `nzb` or `source_subject` into result objects.

Text search uses trigram-compatible case-insensitive matching across normalized title, normalized author, narrator, and source subject. PostgreSQL GIN trigram indexes support those predicates. Filters cover format, download status, and import status. A closed mapping converts supported sort names into SQLAlchemy expressions; user strings are never interpolated into SQL. Every sort includes `id` as a stable tie-breaker.

Full release retrieval remains a separate lookup by ID. PostgreSQL stays authoritative.

## API Contract

`GET /api/releases/search` accepts `q`, `limit`, `offset`, `sort`, `order`, `format`, `download_status`, and `import_status`. `limit` is constrained to 1 through 100 and `offset` is nonnegative. Unsupported values receive FastAPI validation responses.

The response shape is `{total, limit, offset, results}`. Each result contains only list-view fields. `GET /api/releases/{release_id}` returns the full release object or 404. Existing NZB route behavior remains unchanged. In-memory development and test repositories may use a bounded compatibility implementation, while production PostgreSQL requests use `search_page()`.

## Dashboard Reads

Dashboard aggregates are computed with bounded database aggregate queries rather than loading release rows or issuing per-row lookups. The API returns only the counts and status summaries required by the dashboard.

## Failure Handling

Request validation rejects invalid pagination, sort, order, and filter values before repository execution. Missing detail records return 404. Database failures continue through the application's existing error path; PR 4 does not introduce retries or conceal operational errors.

## Verification

Development follows red-green tests for search semantics, response shape, validation, stable ordering, filtering, total counts, detail behavior, schema indexes, and dashboard query behavior. The PostgreSQL benchmark seeds deterministic rows with set-based SQL, runs `ANALYZE`, warms the query, and records p50/p95 separately from fixture creation. The one-million-row selective-search p95 must remain below 150 ms without weakening correctness or reducing the required work.
