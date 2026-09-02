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

LoreX is in initial development. The first milestone is a tested vertical slice:

`mock NNTP headers → audiobook release → search → mocked download → import → library`

The project will use red-green testing and will not begin broad production backfill until that vertical slice passes end-to-end tests.

## Legal use

LoreX is a general-purpose self-hosted tool intended for public-domain, user-owned, or otherwise authorized content. Users are responsible for complying with applicable laws and provider terms.
