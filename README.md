# LoreX

LoreX is a self-hosted audiobook Usenet platform that combines an audiobook-focused NZB indexer, native NNTP downloader, metadata-aware post-processing, and a managed audiobook library in one application.

## Project direction

LoreX is designed as a light-mode sibling to ScarletX with a compact ARR-style interface. The initial release targets a single-user Docker/TrueNAS SCALE deployment and a managed M4B-first library suitable for Apple Books workflows.

### Planned v1 capabilities

- Audiobook-only Usenet indexing with live scan and backfill
- Multipart grouping, obfuscation inspection, deduplication, and NZB generation
- Newznab-compatible audiobook API (`3030`)
- Wanted/monitoring and automatic grabs
- Native multi-provider NNTP downloader with TLS and fill-server fallback
- PAR2 verification/repair and RAR/7z extraction
- Automatic metadata identification and confidence-based matching
- M4B-oriented import pipeline with artwork and chapters
- Managed Author / Series / Title library layout
- Light-mode LoreX web UI
- Docker Compose and TrueNAS SCALE deployment

## Architecture

The initial architecture is a modular monolith:

- **API/backend:** Python + FastAPI
- **Database:** PostgreSQL
- **Queue/cache:** Redis
- **Frontend:** React + TypeScript
- **Media processing:** FFmpeg / FFprobe
- **Repair/extraction:** PAR2, unrar, 7-Zip

Long-running indexer, downloader, and importer work runs in separate worker processes built from the same application image.

## Development status

LoreX is in alpha development. The live NNTP integration includes authenticated TLS connections, provider/fill-server configuration, restart-safe group scanning with persisted checkpoints, XOVER/OVER overview retrieval, streaming BODY downloads, yEnc decoding, and bounded provider concurrency. A deterministic local TLS NNTP fixture exercises the full scan-to-library path without requiring real provider credentials in CI.

External provider credentials are intentionally not stored in source control or CI, so a real-provider smoke test is a deployment validation step rather than part of the public automated test suite.

The project uses red-green testing and a measurement-first optimization program. The first reproducible performance reference is documented in [`docs/performance/baseline-0.1.1-alpha.md`](docs/performance/baseline-0.1.1-alpha.md). Performance changes must compare against the benchmark harness with fresh evidence rather than relying on subjective speed claims.

## Live NNTP configuration

LoreX encrypts NNTP usernames and passwords before storing them in PostgreSQL. The encryption key is supplied separately through `LOREX_CREDENTIAL_KEY`; the key itself is never stored in PostgreSQL.

Before entering provider credentials:

1. Generate one cryptographically random 32-byte credential key and encode it with URL-safe base64 without padding.
2. Store that value as the TrueNAS/container secret or environment variable `LOREX_CREDENTIAL_KEY` for the API and scanner services.
3. Back the credential key up separately from PostgreSQL. Losing the key means existing encrypted provider credentials cannot be recovered and must be re-entered.
4. Never place the credential key in `docker-compose.yml`, committed configuration, screenshots, logs, or source control.

Provider configuration is available under `/api/settings/nntp/providers`. Add the provider hostname, TLS port (normally 563), priority, connection limit, credentials, and one or more enabled audiobook groups. Mark secondary providers as fill servers when they should be tried after the primary provider. The provider test endpoint verifies TLS connection, authentication, and the first enabled configured group without returning stored credentials.

LoreX production NNTP connections require certificate verification. There is no production option that disables TLS verification.

## Legal use

LoreX is a general-purpose self-hosted tool intended for public-domain, user-owned, or otherwise authorized content. Users are responsible for complying with applicable laws and provider terms.
