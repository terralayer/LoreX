# LoreX Optimization PR 2 — Streaming Indexer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace whole-workload indexer assumptions with a bounded streaming pipeline that preserves multipart correctness, explicit checkpointing, deduplication, and lazy NZB generation while measurably improving indexing throughput and memory.

**Architecture:** Keep `ReleaseRepository` as the temporary authoritative in-memory store until PR 3, but add a batch-commit boundary that persists release metadata, article references, and optional checkpoints together after validation. Add a streaming multipart grouper that normalizes each header once, carries only bounded pending groups across input batches, and sends unresolved/evicted candidates to an inspection hook instead of silently indexing them. Accepted releases retain article references and generate/cache NZB XML only on demand.

**Tech Stack:** Python 3.12, dataclasses, FastAPI, pytest, existing benchmark harness and GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-01-whole-app-optimization-design.md`

## Global Constraints

- Optimization program version stays `0.1.1 alpha` / Python `0.1.1a1` / npm `0.1.1-alpha.1`.
- PR order remains serial; this PR must not implement PostgreSQL persistence/search from PR 3/4.
- Backfill/indexing working memory is bounded by configured batch size and pending-group limits, not total header history.
- Correctness work may not be removed merely to improve benchmark numbers.
- Checkpoints may advance only through the batch commit boundary.
- Full NZB documents are generated lazily and cached after first request.
- Existing `index_headers(headers, repository)` remains as a compatibility wrapper.

---

### Task 1: Streaming multipart grouper

**Files:**
- Modify: `backend/lorex/indexer/grouping.py`
- Create: `tests/test_streaming_indexer.py`

**Interfaces:**
- Produces `NormalizedHeader`, `normalize_header()`, and `StreamingHeaderGrouper`.
- `StreamingHeaderGrouper.feed(header)` returns zero or one completed `ReleaseCandidate` values.
- `StreamingHeaderGrouper.flush()` releases unnumbered complete groups and routes numbered incomplete groups to the configured inspection callback.

- [ ] Write failing tests proving a multipart release can span input batches, duplicate parts do not duplicate output, and pending groups cannot exceed the configured limit.
- [ ] Run backend CI and verify the tests fail because the streaming grouper does not exist.
- [ ] Implement one-time subject/part normalization and bounded pending-group handling. Sort only completed multipart parts by explicit part number, where ordering is correctness-critical.
- [ ] Run all backend tests and verify green.

### Task 2: Atomic batch persistence, checkpoints, and overlap dedupe

**Files:**
- Modify: `backend/lorex/domain.py`
- Modify: `backend/lorex/repository.py`
- Modify: `tests/test_streaming_indexer.py`

**Interfaces:**
- Produce immutable `IndexCheckpoint(source: str, group: str, article_number: int)`.
- Produce `ReleaseRepository.commit_index_batch(records, checkpoint=None) -> int` where each record is `(IndexedRelease, tuple[ArticleHeader, ...])`.
- Produce `ReleaseRepository.get_checkpoint(source, group)`, `get_articles(release_id)`, and NZB cache accessors.

- [ ] Add failing tests proving replaying an already indexed release creates no duplicate and a regressing checkpoint rejects the entire batch before mutation.
- [ ] Run backend CI and verify the new assertions fail for missing interfaces.
- [ ] Implement pre-validation plus one batch mutation boundary. Do not copy the full repository per commit.
- [ ] Run all backend tests and verify green.

### Task 3: Streaming indexing service and lazy NZB

**Files:**
- Modify: `backend/lorex/services/indexing.py`
- Modify: `backend/lorex/indexer/nzb.py`
- Modify: `backend/lorex/api/releases.py`
- Modify: `tests/test_streaming_indexer.py`
- Modify: `tests/test_release_api.py`

**Interfaces:**
- Produce `IndexBatch(headers: Iterable[ArticleHeader], checkpoint: IndexCheckpoint | None = None)`.
- Produce `IndexingStats(headers_received, candidates_completed, releases_indexed, releases_rejected, duplicate_releases)`.
- Produce `index_batches(batches, repository, *, batch_size=..., max_pending_groups=..., inspect_candidate=None) -> IndexingStats`.
- Keep `index_headers()` as a compatibility wrapper.
- Produce `get_or_build_nzb(release_id, repository) -> str` and API `GET /api/releases/{release_id}/nzb`.

- [ ] Add failing tests proving indexing across batches is correct, checkpoints commit, replay dedupes, accepted releases do not carry eager NZB XML, the first NZB request builds it, and the second request returns the cached result.
- [ ] Run backend CI and verify red for the missing streaming service/lazy NZB behavior.
- [ ] Implement the minimal service and API behavior; invoke the inspection hook before classification so future progressive obfuscation work remains available.
- [ ] Run all backend tests and verify green.

### Task 4: Benchmark comparison and regression review

**Files:**
- Modify: `benchmarks/scenarios.py`
- Create: `docs/performance/optimization-pr2-streaming-indexer.md`

**Interfaces:**
- Keep scenario name `index_headers` so PR 1 measurements remain comparable.
- Add reported `batch_size` / pending-group configuration in notes where useful.

- [ ] Change the index benchmark to exercise `index_batches()` without changing the logical header workload.
- [ ] Run full CI benchmark on the exact PR head.
- [ ] Compare headers/sec and Python allocation/peak RSS with the fresh PR-1 `main` benchmark; document CPU, memory, disk, database, and API regressions/neutrality.
- [ ] Require >= 25,000 headers/sec on the reference benchmark to claim the PR-2 indexing target; if it misses, profile and optimize within this PR before merge.
- [ ] Confirm frontend build and unrelated backend correctness remain green.
