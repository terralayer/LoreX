# LoreX v1 Design

## Goal

LoreX is a single-user, self-hosted audiobook application combining an audiobook-only Usenet indexer, native NNTP downloader, metadata-aware importer, and managed audiobook library in one light-mode web UI.

## Product identity

- Name: **LoreX**
- UI direction: light-mode sibling of ScarletX
- Visual language: compact ARR-style navigation, dense information cards/tables, purple accent, bright neutral surfaces, audiobook cover art as the primary visual content
- Approved logo: minimalist open-book + headphones icon with `LoreX` wordmark, dark `Lore`, purple-gradient `X`, no TerraLayer text in the mark

## Architecture

Use a modular monolith with one shared backend codebase and distinct worker entry points.

- Backend/API: Python 3.12 + FastAPI
- Database: PostgreSQL
- Queue/cache: Redis
- Frontend: React + TypeScript
- Container runtime: Docker Compose; TrueNAS SCALE is a first-class deployment target
- Media tools: ffmpeg, ffprobe, par2, unrar, 7z

Logical flow:

`NNTP -> Indexer -> Releases/Search/Wanted -> Downloader -> Verify/Extract -> Importer -> Managed Library`

## Indexer

- Connect to one or more TLS NNTP providers.
- Scan configured groups in live and backfill modes.
- Pull headers in batches and group multipart articles into candidate releases.
- Do not retain raw headers long-term after a candidate is resolved.
- Classify audiobook candidates using deterministic signals: M4B/M4A/MP3/FLAC, audiobook/unabridged terms, author/title patterns, narrator/series hints, audio-file ratio, and negative media/software indicators.
- Escalate obfuscated candidates progressively: subject -> filenames -> PAR2 metadata -> archive listing -> contained audio tags when needed.
- Generate and retain NZB XML plus normalized release metadata.
- Deduplicate releases by normalized identity/fingerprint.
- Expose Newznab-compatible endpoints including caps, search, book, details, and get using Audio/Audiobook category 3030.

## Downloader

- Native NNTP downloader; SABnzbd is not required.
- Multiple providers with TLS, connection limits, priority, and fill-server fallback.
- Persistent queue with pause, resume, cancel, retry, reordering, progress, speed, ETA, and history.
- Stream article payloads to disk rather than RAM.
- Pipeline states: queued, downloading, verifying, repairing, extracting, processing, importing, completed, failed.
- Use `/downloads/incomplete`, `/downloads/complete`, `/downloads/processing`, `/downloads/failed`.
- Bundle par2, unrar, 7z, ffmpeg, and ffprobe.
- Record provider health: success/missing rate, failures, throughput, and fallback usage.
- Process completed jobs oldest-first.

## Importer and library

- App owns the managed library.
- Preferred final format: M4B compatible with Apple Books workflows.
- Never re-encode an already-good M4B just to normalize it.
- Prefer lossless remux when compatible; transcode only when necessary.
- Multi-file imports must determine track order from disc/track tags, filenames, and metadata; ambiguous ordering goes to manual identification rather than creating a bad book.
- Metadata matching layers: embedded tags, filenames, Open Library, Google Books, then manual match when confidence is low.
- Strong identifiers such as ISBN/ASIN win; otherwise score title, author, series, series position, narrator, year, and duration.
- Managed layout:
  - Series: `/library/Author/Series/01 - Book Title/Book Title.m4b`
  - Standalone: `/library/Author/Book Title/Book Title.m4b`
- Track books, authors, series, narrators, editions, chapters, media files, metadata confidence, source release, and library path.
- Detect duplicates and alternate editions but never automatically delete them.

## Search, wanted, and quality

- Search by title, author, series, narrator, ISBN, ASIN, and release name.
- Group raw Usenet releases under audiobook identities.
- Monitoring performs an immediate search; unmatched monitored books stay in Wanted.
- When an acceptable indexed release appears, optional automatic grab can enqueue it.
- v1 quality preferences support format priority (M4B, M4A, MP3, FLAC), completion threshold, language, abridged/unabridged preference, size bounds, and narrator preference.

## UI

Primary navigation:

`Home / Search / Wanted / Downloads / Library / Authors / Series / Narrators / Indexer / Activity / Settings`

Dashboard summary cards show library count, wanted count, active downloads, indexed releases, and uptime. Main panels show recent releases, active downloads, wanted matches, indexer status, provider health, and activity.

Settings use one page with collapsible groups: General, Indexer, Newsgroups, NNTP Providers, Downloads, Importing, Library, Metadata, Quality Profiles, Newznab API, Security, Advanced.

Desktop is primary; tablet/mobile support search, library browsing, wanted, downloads, and book details.

## Security and durability

- Encrypt provider passwords/API secrets at rest.
- Never write secrets to logs.
- Strict path sanitization and archive traversal protection.
- Extraction size safeguards.
- Persist checkpoints for indexer and downloader state.
- Importer must verify final library output before deleting source/temporary files.
- PostgreSQL is authoritative; Redis stores only queues, locks, progress, and short-lived cache.

## v1 boundaries

Include single-user operation, indexing, backfill/live scan, Newznab API, search/wanted, native downloader, provider failover, repair/extraction, metadata matching, M4B import, managed library, light-mode UI, Docker Compose, and TrueNAS packaging.

Do not include multi-user accounts, native mobile apps, a full streaming player, recommendations/social features, or general movie/TV/music indexing in the first release.

## First implementation milestone

Prove one complete tested vertical slice before broad crawling:

`mock NNTP headers -> multipart grouping -> audiobook classification -> NZB/release -> search API -> mocked grab/download -> import fixture -> library API`

Development uses red-green tests. Broad production backfill is blocked until the vertical slice passes end-to-end tests.
