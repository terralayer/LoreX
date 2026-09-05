# LoreX Full Audiobook History Index Design

## Goal

Make LoreX build and maintain a private searchable index of every audiobook release available in every enabled audiobook newsgroup on the configured NNTP providers, while continuing to ingest new posts promptly and without downloading audiobook payload bodies until the user grabs a release.

## User-visible behavior

- Every enabled provider group participates in normal live indexing.
- Every enabled provider group has a `Full history` setting. It defaults to enabled for existing and newly created groups.
- After upgrade, LoreX begins crawling available provider history automatically for groups with `Full history` enabled.
- Live scanning always has priority over historical crawling. A due or manually requested live scan runs before the next historical batch.
- Historical progress survives container restarts and resumes without rescanning completed history except for safe idempotent overlap after a crash.
- Search uses the same releases table for live and historical discoveries, so historical releases become searchable as soon as each batch is committed.
- Rejected non-audiobook overview headers are not retained.
- Audiobook bodies are not downloaded during indexing. BODY requests remain download-time only.
- The Indexer page shows live worker health plus per-group historical state, scanned range, cumulative headers, cumulative releases, and completion percentage.

## Scanner architecture

LoreX keeps one scanner worker process. The worker contains two logical lanes:

1. **Live lane** — existing forward-only checkpoint behavior. This lane remains authoritative for staying current.
2. **Historical lane** — a new independent descending cursor per provider/group. It works from the newest available article numbers toward the provider's current low-water retention boundary.

The worker loop follows this priority:

1. refresh heartbeat;
2. run a due or manually requested live pass;
3. otherwise process at most one historical provider/group batch;
4. repeat.

This avoids a second scanner container and avoids consuming an additional persistent NNTP connection while still letting the history crawl run continuously between live scans.

### Historical range algorithm

For one provider/group historical step:

- call `GROUP` and read `low` and `high`;
- if no historical state exists, initialize the historical cursor at `high`;
- choose `end = min(next_high, high)`;
- choose `start = max(low, end - scan_batch_size + 1)`;
- fetch `XOVER start-end`;
- group/classify/index the complete response;
- only after the index transaction succeeds, persist `next_high = start - 1` and increment cumulative counters;
- mark complete when `next_high < current low`.

A crash after release insertion but before cursor persistence can cause a batch to be replayed, but release/article uniqueness makes the replay idempotent. The order is deliberately chosen so a crash cannot create a historical gap.

Provider retention can move while a long crawl is running. Completion therefore uses the provider's current `low` value rather than assuming the initial low-water mark remains fixed.

## Historical state

Add a durable `indexer_backfill_state` table keyed by `(provider_id, group_name)` containing:

- `status`: `idle`, `scanning`, `complete`, or `error`;
- `initial_low` and `initial_high` for progress display;
- `next_high` for the next descending batch;
- cumulative `headers_scanned`;
- cumulative `releases_indexed`;
- `last_started_at`, `last_completed_at`, `last_error`, `updated_at`.

Disabling `Full history` pauses progress but does not erase it. Re-enabling resumes from the stored cursor.

## Provider-group settings

Add `backfill_enabled: bool` to `NntpProviderGroup` and `nntp_provider_groups`, defaulting to `true`.

The old `backfill_days` field is retained in persistence/API compatibility for this alpha line but is no longer exposed as the primary UI control. The full-history crawler does not use an arbitrary day estimate because the current NNTP overview model does not contain a reliable posted timestamp. The UI replaces `Backfill days` with `Full history`.

## Storage compaction

The current `release_articles` layout repeats the full NNTP subject and group on every segment. A deep history crawl can contain tens or hundreds of millions of segments, so new historical data must avoid that repetition.

Add `release_payloads`:

- `id` bigint identity primary key;
- `release_id` foreign key to `releases` with cascade delete;
- `filename` text;
- `group` text;
- unique `(release_id, filename, group)`;
- index on `release_id`.

Extend `release_articles` with nullable `payload_id` referencing `release_payloads`. Make legacy `subject` and `group` nullable.

For newly indexed releases:

- extract the physical payload filename from each article subject;
- store each distinct `(release, filename, group)` once in `release_payloads`;
- store each segment primarily as `release_id`, `payload_id`, `message_id`, and `bytes`;
- leave legacy per-segment `subject` and `group` null.

Existing rows remain readable without a bulk rewrite. Repository reads use the payload row when present and fall back to legacy `subject`/`group` otherwise. For compact rows, `get_articles()` reconstructs a minimal synthetic subject containing the filename. This preserves the current downloader/postprocessor contract: BODY retrieval needs message IDs, NZB generation needs groups and byte counts, and reconstruction needs the physical filename, not the original verbose per-segment subject.

Rejected headers are never written to either table.

## Classification and grouping

Keep the current audiobook classifier policy and obfuscated-archive support. Full history means all audiobook candidates that pass LoreX classification, not all cross-posted content in the source group.

Supported accepted payload families remain M4B, M4A, MP3, FLAC, AAC, RAR/7z/ZIP/PAR-style archives and intentionally obfuscated audiobook archives. Strong software/video signatures remain rejected.

## API

Extend `GET /api/indexer/status` with:

- group `backfill_enabled`;
- group historical status;
- `backfill_initial_low`, `backfill_initial_high`, `backfill_next_high`;
- `backfill_headers_scanned`, `backfill_releases_indexed`;
- `backfill_percent` when a meaningful initial range exists.

Provider create/update APIs accept and return `backfill_enabled`.

`POST /api/indexer/scan-now` remains a live-scan trigger and does not reset historical state.

## UI

On Settings > provider groups:

- keep `Scan`;
- keep batch size;
- replace the visible `Backfill days` input with a `Full history` checkbox, default checked.

On Indexer:

- retain current live worker health and Scan Now behavior;
- show live checkpoint separately from historical progress;
- display `History: complete`, `History: paused`, `History: scanning`, or percentage/progress;
- show cumulative historical headers and releases.

## Performance and safety constraints

- Never materialize provider retention history in memory; process one configured overview window at a time.
- Never store rejected overview headers.
- Never issue BODY during indexing.
- Keep live scan latency bounded by giving live work priority over backfill work.
- Persist historical progress only after successful indexing of the fetched window.
- Preserve encrypted provider credentials and the existing `LOREX_CREDENTIAL_KEY` mechanism unchanged.
- Preserve automatic Alembic migrations on container startup.
- Existing release/article rows remain valid and downloadable after migration.
- No database-volume reset or credential rewrite is required for upgrade.

## Testing

Backend tests must cover:

- descending range selection and completion at provider low-water mark;
- independent live and historical cursors;
- live scan priority over historical work;
- historical resume after restart;
- idempotent historical replay;
- pause/resume through `backfill_enabled`;
- compact payload persistence with filename deduplication;
- legacy article-row compatibility;
- reconstructed articles still generate valid NZB metadata and post-processing filenames;
- no BODY requests during indexing;
- status API historical fields and percentages.

Frontend tests must cover provider Full history editing and Indexer historical progress rendering.

CI must pass backend, frontend, packaging, and benchmark gates before merge.
