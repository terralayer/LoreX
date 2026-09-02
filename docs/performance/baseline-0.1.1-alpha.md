# LoreX 0.1.1 Alpha Performance Baseline

## Status

This is the first measurement baseline for the locked LoreX whole-app optimization program. It records the current implementation before production performance algorithms are changed.

The measurements below came from GitHub Actions run `33590249228` on commit `4f2c24af4b47abc8e3248670e6104a717b62c446`. The uploaded `lorex-benchmark-baseline` artifact has SHA-256 digest `31f9134ddeddfafd8232db2f225413d3a63d77ad352ab306f21c620b317a3024`.

These values are engineering baselines, not product performance claims. Later optimization PRs must compare against the relevant scenario using fresh measurements from the same harness.

## Reference Environment

- Product: `LoreX 0.1.1 alpha`
- GitHub hosted runner OS: Ubuntu 24.04.4 LTS
- Runner image: `ubuntu-24.04` version `20260823.283.1`
- Azure runner region for this measurement: `eastus`
- Python: `3.12.14`
- Node: `20.20.2`
- npm: `10.8.2`
- Benchmark platform string: `Linux-6.17.0-1022-azure-x86_64-with-glibc2.39`
- Machine: `x86_64`
- Benchmark profile: `ci`

## Measured Backend Baseline

| Scenario | Scale | Unit | p50 ms | p95 ms | Mean ms | Throughput/sec | Peak Python MB | Process peak RSS MB |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `index_headers` | 10,000 | headers | 1,045.504 | 1,050.609 | 1,045.504 | 9,564.8 | 4.18 | 59.33 |
| `index_headers` | 100,000 | headers | 10,853.757 | 10,853.757 | 10,853.757 | 9,213.4 | 43.39 | 160.42 |
| `group_and_classify` | 10,000 | headers | 153.145 | 153.167 | 153.145 | 65,297.5 | 3.49 | 160.42 |
| `group_and_classify` | 100,000 | headers | 1,619.467 | 1,619.467 | 1,619.467 | 61,748.7 | 16.50 | 160.42 |
| `release_search` | 10,000 | releases | 28.904 | 29.012 | 28.916 | 345,830.9 | 0.08 | 160.42 |
| `release_search` | 100,000 | releases | 290.750 | 291.956 | 290.920 | 343,737.4 | 0.76 | 160.42 |
| `release_search` | 1,000,000 | releases | 2,926.132 | 3,014.778 | 2,947.949 | 339,218.9 | 7.63 | 624.58 |
| `release_search_api` | 10,000 | releases | 32.538 | 45.350 | 35.757 | 279,665.6 | 0.13 | 624.58 |
| `release_search_api` | 100,000 | releases | 288.995 | 290.797 | 288.751 | 346,319.4 | 0.81 | 624.58 |
| `queue_roundtrip` | 10,000 | jobs | 107.257 | 107.483 | 107.257 | 186,468.2 | 1.67 | 624.58 |
| `mock_downloader` | 10,000 | downloads | 59.701 | 59.828 | 59.701 | 167,501.1 | 0.00 | 624.58 |
| `library_importer` | 10,000 | imports | 145.882 | 147.407 | 145.882 | 68,548.5 | 2.89 | 624.58 |

### Memory interpretation

`Peak Python MB` is the peak Python allocation observed by `tracemalloc` while each timed scenario runs. `Process peak RSS MB` is the operating system high-water RSS for the benchmark process, so it is cumulative across scenarios rather than a per-scenario delta. The jump to `624.58 MB` occurs after constructing the one-million-release synthetic catalog and remains the process high-water mark for subsequent scenarios.

## Frontend Production Build Baseline

The production Vite build contained four files as counted recursively by the benchmark collector:

- Raw bytes: `160,621`
- Deterministic gzip bytes: `51,707`

Vite reported the primary generated assets as approximately:

- JavaScript: `151.61 kB` raw / `48.67 kB` gzip
- CSS: `6.71 kB` raw / `2.14 kB` gzip
- HTML: `0.44 kB` raw / `0.28 kB` gzip

The benchmark collector, not Vite's rounded console values, is authoritative for future automated comparisons.

## Baseline Findings

### 1. Search is clearly linear and misses the target at scale

The deterministic needle is placed at the tail of the generated catalog. Search p95 grows from `29.012 ms` at 10K releases to `291.956 ms` at 100K and `3,014.778 ms` at 1M. That is approximately linear growth and is far above the locked eventual search target of `<150 ms p95` at one million releases.

This matches the current implementation: `ReleaseRepository.search()` copies all repository values and case-fold/scans title, author, narrator, and source subject for every normal query. PR 3/4 must replace this path with indexed persistent search rather than micro-optimizing the Python scan.

### 2. Full indexing is much slower than grouping/classification alone

Grouping plus classification measured about `61.7K headers/sec` at 100K headers, while the full `index_headers` path measured about `9.2K headers/sec`. The full path therefore has substantial work outside classification, including identity parsing, release construction, repository writes, and eager NZB construction.

The locked eventual indexing target is at least `25K headers/sec` on the reference benchmark environment after the relevant indexing work lands. The current full path does not meet that target.

### 3. Current indexing retains whole batches and sorts them

The current grouping function receives a complete `list[ArticleHeader]`, groups the entire list in memory, sorts multipart headers by message ID, then sorts all candidates by normalized subject. This baseline does not yet establish bounded memory behavior for arbitrarily long backfills. PR 2 is responsible for introducing bounded batches/checkpoints and comparing both throughput and memory against this baseline.

### 4. NZBs are built eagerly during indexing

Every accepted audiobook currently calls `build_nzb(candidate)` during indexing. That work occurs even when the release is never requested or grabbed. The locked architecture calls for storing sufficient article references and generating/caching the full NZB lazily; later PRs must prove the benefit against the full-index baseline above without weakening correctness.

### 5. The queue has an O(n) head removal

`JobRepository.pop_next()` uses Python list `pop(0)`. A complete drain therefore becomes O(n²), which is why PR 1 intentionally caps the queue round-trip scenario at 10K jobs. The 10K baseline is `107.483 ms p95`; PR 5 must replace the queue architecture rather than treating this bounded fixture number as evidence that the current structure scales.

### 6. API timing currently inherits repository search cost

LoreX does not yet have the planned lightweight dashboard aggregate endpoint, so PR 1 uses `/api/releases/search` as its representative read-API benchmark. At 100K releases that endpoint measured `290.797 ms p95`, essentially tracking the underlying linear repository scan. Later read/API work must add indexed persistence, lightweight projections, pagination, and dedicated aggregate queries before dashboard targets can be evaluated directly.

### 7. Downloader and importer numbers are fixture costs only

The current downloader is a mock that copies release metadata into a `DownloadResult`; it does not perform NNTP network I/O, streaming writes, provider fallback, or TLS connection work. The current importer constructs sanitized paths and in-memory library records; it does not yet perform real PAR2, extraction, FFmpeg, tagging, artwork, verification, or filesystem movement.

Their PR 1 numbers are useful only as regression baselines for the current fixture operations. PRs 5 and 6 must introduce separate realistic I/O/media fixtures before making downloader or importer throughput claims.

## Comparison Rules for PRs 2–8

- Use the deterministic benchmark generators and fixed seeds established by PR 1.
- Compare the same scenario and scale before and after a performance change.
- Add a new scenario before claiming an improvement in a workload not represented here.
- Do not change fixture work merely to make a benchmark faster.
- Correctness tests remain hard gates.
- Timing thresholds remain informational until enough runner history exists to distinguish real regressions from hosted-runner variance.
- For memory comparisons, prefer scenario-specific Python peaks and explicitly account for the cumulative nature of process high-water RSS.

## Benchmark Artifact

The CI job publishes `benchmark-results/baseline.json` and `benchmark-results/baseline.md` in the `lorex-benchmark-baseline` workflow artifact. The JSON file is the machine-readable source for future automated comparison tooling.
