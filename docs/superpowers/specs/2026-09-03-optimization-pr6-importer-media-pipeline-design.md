# LoreX Optimization PR 6 — Importer and Media Pipeline Efficiency Design

## Status

Approved in chat on 2026-09-03.

## Goal

Build a recoverable, bounded, measurement-backed audiobook import/media pipeline that verifies downloaded content, safely repairs/extracts archives, preserves valid M4B without re-encoding, remuxes when possible, tags and verifies final output, atomically promotes the result into the managed library, and deletes source material only after verified success.

## Scope

This PR implements only serial Optimization PR 6. Metadata caching/coalescing (PR 7) and UI/API responsiveness (PR 8) remain out of scope.

## Architecture

Importer work is represented by durable PostgreSQL import-job state. Completed downloads enter the importer in oldest-completed-first order. Workers claim jobs with row locking and bounded concurrency, then advance through explicit recoverable stages:

`queued -> verifying -> repairing -> extracting -> probing -> processing -> tagging -> final_verification -> moving -> completed`

Failure records the stage and error without deleting source material. Stale claims may be recovered back to queued work.

The media pipeline is split into focused units:

- `import_queue.py`: durable job claiming, stage/status updates, recovery, oldest-first ordering.
- `archive.py`: archive traversal validation and extracted-size/file-count limits.
- `tools.py`: bounded subprocess execution for PAR2, FFprobe, FFmpeg and tagging adapters.
- `media.py`: probe and preserve/remux/transcode decision rules.
- `pipeline.py`: orchestration, staging, final verification, atomic promotion and cleanup.
- existing `importer.py`: library record/path generation after successful final media verification.

## Persistent State

Extend `import_jobs` with:

- `source_path`, `staging_path`, `final_path`
- `stage`
- `claimed_at`, `claimed_by`
- `created_order` identity for oldest-first ordering
- `started_at`, `completed_at`, `updated_at`
- `error`
- wall/CPU/temp-disk metric fields sufficient for benchmark and diagnosis

PostgreSQL remains authoritative. Redis is not required for PR 6.

## Safety and Correctness

- Source cleanup never occurs before final output verification succeeds.
- Archive entries with absolute paths, `..` traversal, symlink escape, excessive file count, or configured extracted-size overflow are rejected.
- Extraction is confined to a per-job staging directory.
- Promotion prefers an atomic same-filesystem rename. Cross-filesystem promotion uses copy-to-temporary, flush/fsync, verification, atomic rename at destination, then source cleanup.
- A valid M4B is preserved without re-encoding.
- Compatible audio needing only container normalization uses FFmpeg stream copy (`-c copy`).
- Re-encoding is a fallback only when probe evidence requires it.
- PAR2/FFmpeg/extraction concurrency is bounded separately from downloader concurrency.
- Failed or interrupted jobs retain durable stage/source state and are restartable.

## Processing Policy

1. Verify downloaded parts/files and determine whether repair is required.
2. Run PAR2 only when recovery data exists and verification indicates repair is needed.
3. Validate archives before extraction; enforce traversal, count and expanded-size limits.
4. Probe candidate media with FFprobe.
5. If already valid M4B, preserve it.
6. If codecs are compatible but container is not preferred, remux to M4B with stream copy.
7. Re-encode only when required for a playable supported output.
8. Apply tags/chapters through the media tooling adapter.
9. Probe and verify the final staged file.
10. Promote into the sanitized managed-library path.
11. Persist the library row.
12. Delete source/staging material only after the final file and library record are confirmed.

## Resource Isolation

`MediaWorkerLimits` configures independent maximum concurrent tasks for repair, extraction and FFmpeg work. Defaults remain conservative and every value must be positive. Pipeline orchestration must not create unbounded futures or read whole media files into Python memory.

## Benchmark and Acceptance Gates

PR 6 must extend the benchmark harness with deterministic importer/media fixtures and report:

- wall time
- process CPU time
- temporary disk bytes/peak
- bytes copied
- preserve/remux/transcode counts
- oldest-first claim behavior

The benchmark compares the existing metadata-only importer baseline where relevant and, more importantly, separates unavoidable external-tool/disk work from Python overhead. The optimization is accepted only with fresh exact-head CI, passing correctness tests, bounded-resource evidence, and no safety regression.

## Out of Scope

- metadata provider lookups/cache/coalescing
- artwork fetching
- UI changes
- streaming playback
- multi-user scheduling
- distributed worker orchestration
