# LoreX Live NNTP Integration Evidence

Date: 2026-09-04

Implementation evidence run: GitHub Actions CI `33895329029` on commit `138b559ada0b11d9ca681361e1ca0c332e841f12`.

## Correctness and security gates

- Backend suite: passed, including deterministic fake-TLS end-to-end scan/download/import coverage and NNTP credential/security tests.
- Frontend production build: passed.
- Provider credentials are encrypted at rest with AES-GCM; the credential key is supplied separately through `LOREX_CREDENTIAL_KEY` and is not persisted in PostgreSQL.
- Production NNTP connections use certificate-verifying TLS with SNI.
- NNTP command arguments reject CR/LF injection.
- Scanner checkpoints are persisted only after a complete overview response has been received and committed.
- BODY responses and yEnc payloads are processed incrementally rather than buffered as whole articles.
- Provider concurrency remains bounded by each provider's configured `max_connections`.
- Primary/fill behavior reuses the existing provider/downloader fallback path; authentication and protocol failures remain hard failures rather than silent fallback.
- The explicit `/api/index/mock` development path is isolated from production live-NNTP downloads.

## Live NNTP benchmark

Deterministic in-process transport fixtures; these numbers validate parser/streaming behavior and memory bounds, not external Usenet network speed.

| Scenario | Result | Gate |
| --- | ---: | ---: |
| Overview rows parsed | 10,000 | 10,000 |
| Overview elapsed | 142.746 ms | informational |
| Overview throughput | 70,054.3 rows/sec | informational |
| Overview peak Python allocation | 0.002 MiB | <32 MiB |
| BODY bytes streamed | 67,108,864 bytes (64 MiB) | 64 MiB |
| BODY elapsed | 2.197 ms | informational |
| BODY synthetic throughput | 29,125.5 MiB/sec | informational; no network latency |
| BODY peak Python allocation | 0.001 MiB | <8 MiB |
| Provider configured max connections | 4 | 4 |
| Provider observed maximum | 4 | <= configured maximum |
| Concurrent requests exercised | 24 | informational |

All live-NNTP benchmark gates passed.

## Existing whole-app regression gates

The same CI run also executed the existing benchmark chain after the live-NNTP changes:

- 100,000-header indexing: **33,925.5 headers/sec**, above the 25,000 headers/sec gate.
- PostgreSQL 1,000,000-release search: **83.687 ms p95**, below the 150 ms gate.
- Dashboard aggregate: **23.023 ms p95**, below the 250 ms gate.
- Deep paged library read at offset 50,000: **22.019 ms p95**, below the 100 ms normal-read gate.
- Initial JavaScript entry: **148,610 raw bytes / 48,008 deterministic gzip bytes**, with five lazy chunks; still below the PR1 primary-JS baseline.
- Streaming downloader 64 MiB synthetic workload: **0.09 MiB peak Python allocation** in the existing baseline harness.
- Progress persistence reduction remained **99.600%**.

## End-to-end fixture

The deterministic TLS fixture proves the application-level chain without public-provider credentials:

`TLS NNTP authentication → GROUP/XOVER → ArticleHeader → PostgreSQL release/articles → queued grab → primary BODY attempt → fill-server fallback → streaming yEnc decode → staged article files → library import`

The fixture intentionally makes the primary provider miss one multipart article and verifies that the configured fill provider supplies it.

## Deployment validation boundary

CI does not contain Astraweb, Newshosting, or other real-provider credentials. Therefore this evidence establishes code correctness against a certificate-validating local TLS NNTP server, but does **not** claim a completed external-provider smoke test. A deployment should use the provider test endpoint after configuring `LOREX_CREDENTIAL_KEY` and the user's real provider credentials.
