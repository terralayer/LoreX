# LoreX Optimization PR 1 — Benchmark Harness and Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, non-flaky benchmark harness that measures the current LoreX `0.1.1 alpha` implementation and publishes reproducible baseline artifacts before any production optimization work begins.

**Architecture:** Keep all benchmark-only code outside production request paths under `benchmarks/`. Synthetic datasets are generated from fixed seeds, benchmark measurements are emitted as JSON plus Markdown, and GitHub Actions runs correctness tests as hard gates while publishing performance results without enforcing timing thresholds yet. Production behavior remains unchanged in this PR except for synchronizing version metadata to the approved alpha version.

**Tech Stack:** Python 3.12, FastAPI/TestClient, standard-library timing/memory tools, React/Vite build output, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-01-whole-app-optimization-design.md`

## Global Constraints

- Product/UI version: `0.1.1 alpha`.
- Python package version: `0.1.1a1`.
- npm package version: `0.1.1-alpha.1`.
- Measurement must precede tuning; this PR does not optimize production algorithms.
- Synthetic data must be deterministic from a fixed seed.
- Benchmarks must not make correctness CI flaky; no wall-clock performance threshold is a merge gate in PR 1.
- PostgreSQL remains the future authoritative persistent store; this PR measures the current in-memory baseline only.
- Large benchmark fixtures must be generated, not committed.
- Capture headers/sec, grouping/classification throughput, peak Python memory, release search p50/p95, representative API p50/p95, queue throughput, downloader fixture throughput, importer fixture time, and frontend production build size.
- Exercise 10K, 100K, and 1M logical scales where practical; document where a current algorithm makes a scale intentionally impractical rather than hiding it.

---

### Task 1: Lock the approved alpha version in executable metadata

**Files:**
- Create: `tests/test_version.py`
- Modify: `pyproject.toml`
- Modify: `backend/lorex/__init__.py`
- Modify: `frontend/package.json`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Produces: a single version contract: Python `0.1.1a1`, npm `0.1.1-alpha.1`, UI `v0.1.1 alpha`.

- [ ] **Step 1: Write a failing version-consistency test** that reads the three machine-readable/text version sources and asserts the approved values.
- [ ] **Step 2: Run `pytest tests/test_version.py -q` in CI and verify RED** because `main` still reports `0.0.1`.
- [ ] **Step 3: Update the four version sources to the approved alpha values.**
- [ ] **Step 4: Run the version test and full correctness suite and verify GREEN.**
- [ ] **Step 5: Commit the version synchronization.**

### Task 2: Add benchmark result primitives and deterministic timing utilities

**Files:**
- Create: `benchmarks/__init__.py`
- Create: `benchmarks/metrics.py`
- Create: `tests/test_benchmark_metrics.py`

**Interfaces:**
- Produces: `percentile(values: list[float], q: float) -> float`, `measure_samples(name: str, fn: Callable[[], object], samples: int, warmups: int = 1) -> BenchmarkResult`, and `BenchmarkResult.to_dict()`.

- [ ] **Step 1: Write failing tests** for p50/p95 interpolation, sample count, non-negative elapsed times, and stable JSON fields.
- [ ] **Step 2: Run the focused test and verify RED** because `benchmarks.metrics` does not exist.
- [ ] **Step 3: Implement only the tested timing/result behavior** using `time.perf_counter`, `tracemalloc`, and process high-water RSS reporting where available.
- [ ] **Step 4: Re-run focused tests and verify GREEN.**
- [ ] **Step 5: Commit the benchmark primitives.**

### Task 3: Add deterministic synthetic LoreX datasets

**Files:**
- Create: `benchmarks/datasets.py`
- Create: `tests/test_benchmark_datasets.py`

**Interfaces:**
- Produces: `generate_headers(count: int, seed: int = 1101) -> list[ArticleHeader]`, `populate_releases(count: int, seed: int = 1101) -> ReleaseRepository`, `populate_jobs(count: int) -> JobRepository`, and `generate_download_results(count: int, seed: int = 1101) -> list[DownloadResult]`.

- [ ] **Step 1: Write failing tests** proving identical seed/count inputs generate identical IDs/subjects, counts are exact, and generated search data contains a deterministic needle near the end of the catalog.
- [ ] **Step 2: Run the focused test and verify RED.**
- [ ] **Step 3: Implement deterministic generators** without committing generated fixture blobs.
- [ ] **Step 4: Re-run focused tests and verify GREEN.**
- [ ] **Step 5: Commit dataset generation.**

### Task 4: Build the backend benchmark scenarios and report writer

**Files:**
- Create: `benchmarks/scenarios.py`
- Create: `benchmarks/run_baseline.py`
- Create: `tests/test_benchmark_runner.py`

**Interfaces:**
- Consumes: Task 2 metrics and Task 3 datasets.
- Produces: `run_suite(profile: str) -> dict`, JSON output at `benchmark-results/baseline.json`, Markdown output at `benchmark-results/baseline.md`.

- [ ] **Step 1: Write failing tests** for report schema, deterministic scenario names, JSON/Markdown file creation, and a `smoke` profile small enough for unit tests.
- [ ] **Step 2: Run focused tests and verify RED.**
- [ ] **Step 3: Implement scenarios** for header indexing/grouping/classification, release search, representative release-search API calls, queue enqueue/dequeue, mock downloader operations, and importer operations.
- [ ] **Step 4: Define a CI profile** that measures 10K/100K indexing where practical and 10K/100K/1M release search, while keeping pathological current O(n²) queue drain work bounded and explicitly labeling the tested queue size.
- [ ] **Step 5: Re-run focused tests and full backend tests and verify GREEN.**
- [ ] **Step 6: Commit backend benchmark scenarios.**

### Task 5: Capture frontend production bundle size and publish CI artifacts

**Files:**
- Create: `benchmarks/frontend_size.py`
- Create: `tests/test_frontend_size.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: frontend file count/raw bytes/gzip-estimate fields merged into the benchmark JSON/Markdown and a GitHub Actions artifact named `lorex-benchmark-baseline`.

- [ ] **Step 1: Write a failing test** against a temporary synthetic `dist/` tree to validate byte counting and deterministic output ordering.
- [ ] **Step 2: Run the focused test and verify RED.**
- [ ] **Step 3: Implement the frontend size collector.**
- [ ] **Step 4: Add a separate `benchmark` CI job** that installs backend dependencies, builds the frontend, runs the CI benchmark profile, appends frontend build-size data, prints the Markdown report to the job summary, and uploads `benchmark-results/` with `actions/upload-artifact@v4`.
- [ ] **Step 5: Keep backend/frontend correctness jobs as hard gates; benchmark results are recorded but no timing threshold is enforced.**
- [ ] **Step 6: Verify tests and workflow execution are GREEN.**
- [ ] **Step 7: Commit CI/artifact integration.**

### Task 6: Record the first measured baseline from the reference CI runner

**Files:**
- Create: `docs/performance/baseline-0.1.1-alpha.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: exact benchmark artifact produced by the final PR head before this documentation commit.
- Produces: durable baseline values and environment notes that PRs 2–8 must compare against.

- [ ] **Step 1: Run CI on the implementation head and retrieve the generated benchmark artifact/job output.**
- [ ] **Step 2: Inspect results for missing metrics, zero/invalid values, or scale labels that do not match the workload. Fix the harness first if any are found.**
- [ ] **Step 3: Write the baseline document with exact measured values, runner/Python/Node context, and explicit observations about current linear search, whole-batch indexing, eager NZB generation, and list-head queue removal.**
- [ ] **Step 4: Link the baseline document from README development/performance documentation.**
- [ ] **Step 5: Run fresh CI on the exact final head and require backend tests, frontend build, and benchmark job to complete successfully.**
- [ ] **Step 6: Commit the measured baseline documentation.**

## Self-Review

- Spec coverage: all required PR 1 metrics are represented; 1M scale is required for release search and generated logical catalog data, while workloads known to be pathological or memory-heavy are bounded and labeled rather than silently skipped.
- Placeholder scan: no TBD/TODO implementation placeholders are allowed in the delivered files or plan.
- Type consistency: benchmark result/report APIs are defined once in Tasks 2–4 and reused by CI/reporting tasks.
- Scope: production algorithms are deliberately unchanged; PR 2 begins streaming-indexer optimization only after this baseline is merged.
