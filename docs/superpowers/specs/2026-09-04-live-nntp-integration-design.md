# LoreX Live NNTP Integration Design

## Status

Approved in chat on 2026-09-04 with encrypted PostgreSQL provider credentials.

## Goal

Replace LoreX's mock NNTP boundary with a real, restart-safe TLS NNTP transport that can scan audiobook groups, persist headers/checkpoints, and stream article bodies into the existing bounded downloader pipeline without weakening the performance and recovery guarantees established by Optimization PRs 1-8.

## Scope

This design adds one production subsystem with four responsibilities:

1. encrypted provider configuration persisted in PostgreSQL;
2. a LoreX-owned TLS NNTP protocol client;
3. bounded live/backfill header scanning using transactional PostgreSQL checkpoints;
4. production wiring from stored providers into the existing `ArticleProvider` and downloader interfaces.

The first implementation does not add a new queue system, replace PostgreSQL, alter the importer/media pipeline, or redesign the frontend. A settings UI may consume the provider API later; this PR must expose safe provider CRUD/test operations without returning plaintext secrets.

## Security Model

### Credential storage

Provider usernames and passwords are stored encrypted in PostgreSQL. Encryption uses AES-256-GCM with a random 96-bit nonce per encrypted value and authenticated additional data that binds each ciphertext to its provider ID and field name.

The database stores a versioned envelope containing:

- encryption version (`v1`);
- nonce;
- ciphertext plus GCM authentication tag.

The database never stores the credential master key.

LoreX receives exactly one 32-byte credential master key through the runtime secret `LOREX_CREDENTIAL_KEY`. The value is base64url-encoded and supplied by Docker/TrueNAS secret injection or an equivalent protected environment mechanism. Startup fails closed for operations that require decrypting provider credentials when the key is missing or malformed.

This separation is mandatory: a database dump must not be sufficient to recover provider credentials.

### Secret handling rules

- plaintext usernames/passwords may exist only transiently in process memory;
- plaintext credentials are never logged;
- API reads never return plaintext credentials;
- provider API responses expose only booleans such as `username_configured` / `password_configured`;
- updating a provider without supplying a new credential preserves the existing encrypted value;
- deleting/clearing a credential requires an explicit clear operation;
- exception text from authentication failures must not include submitted credentials;
- benchmark fixtures and CI use fake credentials only.

### Key rotation

The envelope is versioned so future key rotation can be implemented without changing provider records. Automatic online key rotation is out of scope for this first live-NNTP PR.

## Persistent Provider Model

Add a PostgreSQL `nntp_providers` table with one row per provider.

Required fields:

- `id`: stable generated provider ID;
- `name`: unique display name;
- `host`;
- `port`, default `563`;
- `tls`, required `true` in v1;
- `enabled`;
- `priority`;
- `fill_server`;
- `max_connections`;
- `username_encrypted`;
- `password_encrypted`;
- `created_at`;
- `updated_at`.

Add a child `nntp_provider_groups` table with:

- `provider_id`;
- `group_name`;
- `enabled`;
- `scan_batch_size`;
- `backfill_days` or equivalent bounded backfill policy metadata if needed by the scanner.

Provider/group configuration is authoritative in PostgreSQL. Existing `indexer_checkpoints` remain the authoritative scan position and continue to be keyed by `source` + `group`; `source` becomes the provider ID for live NNTP scans.

## Provider Configuration API

Add provider management endpoints under `/api/settings/nntp/providers`.

Required operations:

- list providers with masked credential state;
- create provider;
- update provider fields and optionally replace encrypted username/password;
- explicitly clear one credential;
- delete provider only when no active operation is using it;
- test provider connection/authentication without persisting plaintext results.

Validation rules:

- TLS is mandatory;
- port must be 1-65535;
- `max_connections` must be positive and bounded by a conservative application maximum;
- priority must be deterministic and sortable;
- group names must be non-empty and normalized for comparison;
- provider names are unique;
- test-connection responses contain protocol/auth status but no server text that could echo credentials.

## NNTP Transport

Implement a small LoreX-owned synchronous NNTP client using Python `socket` and `ssl` rather than deprecated `nntplib`.

### Connection lifecycle

For each connection:

1. resolve/connect to the configured host/port;
2. wrap with a certificate-validating TLS context;
3. read and validate the server greeting;
4. authenticate with `AUTHINFO USER` / `AUTHINFO PASS` when credentials are configured;
5. issue commands through one line-oriented protocol parser;
6. close cleanly with `QUIT` where practical, while tolerating abrupt remote disconnects.

TLS certificate verification is enabled by default and cannot be disabled through normal provider configuration in v1.

### Supported commands

The initial production client implements only the commands LoreX needs:

- `AUTHINFO USER` / `AUTHINFO PASS`;
- `GROUP`;
- `XOVER` (with `OVER` fallback only if required by a tested provider capability path);
- `BODY`;
- `QUIT`.

No posting/upload commands are implemented.

### Protocol correctness

The parser must:

- enforce a maximum response-line length;
- support multiline responses terminated by a single `.` line;
- unescape NNTP dot-stuffed lines (`..` -> `.`);
- preserve BODY bytes without decoding the full article into memory;
- classify protocol response codes into authentication, unavailable-article, temporary-provider, and permanent-configuration failures;
- place connect/read timeouts on all network operations.

## Header Scanning

Add a scanner service that consumes one enabled provider/group at a time using bounded batches.

### Scan flow

1. load provider configuration and decrypt credentials through the credential service;
2. connect/authenticate;
3. issue `GROUP` and obtain server low/high article numbers;
4. load `IndexCheckpoint(source=provider_id, group=group_name)` from PostgreSQL;
5. choose the next bounded article-number range;
6. request `XOVER start-end`;
7. convert valid overview records into `ArticleHeader` objects;
8. pass one `IndexBatch(headers=..., checkpoint=...)` into the existing `index_batches` pipeline;
9. advance the checkpoint only through the highest successfully processed article number represented by that committed batch;
10. repeat until the configured live/backfill bound is reached.

### Checkpoint rules

- checkpoints never move backwards;
- a failed database commit does not advance the checkpoint;
- a network disconnect before a batch commit causes that range to be retried;
- missing overview rows do not create fake headers, but the persisted checkpoint may advance across successfully queried sparse ranges only after the range itself has been fully received and committed;
- provider ID, not display name, identifies the checkpoint source so renaming a provider does not restart scanning.

### Overview mapping

At minimum map:

- article message ID -> `ArticleHeader.message_id`;
- subject -> `ArticleHeader.subject`;
- bytes -> `ArticleHeader.bytes`;
- selected group -> `ArticleHeader.group`.

Malformed rows are rejected with counters rather than crashing the whole scan batch.

## Downloader Integration

Implement `NntpArticleProvider`, satisfying the existing `ArticleProvider.stream_article(message_id) -> Iterator[bytes]` protocol.

`NntpArticleProvider`:

- acquires a configured provider connection through the existing bounded `ProviderPool` path;
- authenticates using decrypted DB credentials;
- issues `BODY <message-id>`;
- streams article content incrementally as byte chunks;
- translates a missing article into `ArticleUnavailable` so existing provider/fill fallback continues automatically;
- translates retryable network/server failures into `ProviderTemporaryError`;
- never buffers a complete article in memory.

The existing PR5 `ProviderSet` retains ordering semantics:

1. non-fill providers before fill providers;
2. lower numeric priority first;
3. stable provider name tie-breaker.

No downloader fallback algorithm is duplicated inside the NNTP client.

## Production Wiring

Replace `MockDownloader` as the production PostgreSQL container default only when at least one enabled NNTP provider is configured.

The dependency boundary is explicit:

- provider repository loads encrypted provider rows;
- credential service decrypts secrets using `LOREX_CREDENTIAL_KEY`;
- provider factory creates `ProviderConfig` + `NntpArticleProvider` instances;
- `ProviderSet` and `StreamingDownloader` remain the downloader orchestration layer;
- mock/fake providers remain available to tests and development fixtures.

A deployment with no configured live provider must remain bootable for UI/configuration access; operations that require a provider return an explicit configuration error instead of silently using mock downloads.

The legacy `/downloads/process-next` compatibility path must stop pretending a mock download is a real production success once live provider mode is enabled. Production download processing must resolve the release's persisted article list and use the streaming downloader.

## Worker Boundary

Header scanning is a long-running worker responsibility, not a web-request loop. Add a worker entry point that can run:

- one bounded live-scan iteration;
- one bounded backfill iteration;
- repeated scheduled iterations with a sleep interval configured outside the DB or through a small scanner settings record.

A worker crash must be safe because progress is represented by transactional PostgreSQL checkpoints.

## Error Handling and Provider Health

Map failures consistently:

- DNS/connect/TLS timeout or transient 4xx-style server condition -> temporary provider failure;
- authentication rejection -> provider authentication/configuration failure;
- missing article -> `ArticleUnavailable` and fallback;
- malformed protocol response -> provider protocol failure;
- invalid/missing credential key -> local configuration failure; do not mark remote provider unhealthy.

Reuse existing provider-health accounting for download attempts/fallbacks. Add scanner counters for:

- connection attempts/failures;
- auth failures;
- headers received;
- malformed overview rows;
- batches committed;
- checkpoint article number;
- scan duration.

Do not log raw BODY content or full XOVER subjects at normal log level.

## Testing Strategy

### Deterministic fake NNTP server

CI must not require public Usenet access. Add a local fake NNTP server fixture with a test TLS certificate trusted only by the test client context.

The fixture must support scripted:

- greeting;
- authentication success/failure;
- `GROUP` low/high responses;
- multiline `XOVER` rows;
- `BODY` payloads;
- dot-stuffing;
- missing-article responses;
- temporary errors;
- connection drops mid-overview and mid-body;
- delayed responses for timeout tests.

### Required red-green contracts

Credential persistence:

- database values are not plaintext;
- ciphertext decrypts only with the correct master key;
- wrong key/authenticated-data tampering fails closed;
- API reads return masked configuration only;
- credential update preserves unspecified existing secrets.

Protocol client:

- TLS certificate validation;
- AUTHINFO flow;
- GROUP parsing;
- XOVER multiline parsing;
- dot unstuffing;
- BODY streaming in bounded chunks;
- line/timeout limits;
- error-code classification.

Scanner:

- starts from the persisted checkpoint;
- commits bounded batches;
- resumes after disconnect without skipping an uncommitted range;
- does not move checkpoints backward;
- handles sparse/malformed XOVER rows safely;
- provider rename does not reset checkpoint state.

Downloader:

- real `NntpArticleProvider` satisfies existing streaming contract;
- missing article falls through to fill provider;
- temporary primary failure falls through according to existing policy;
- large BODY fixtures do not produce whole-payload Python allocations.

End-to-end fixture:

`fake TLS NNTP -> XOVER -> ArticleHeader -> index_batches -> PostgreSQL release/articles -> grab -> StreamingDownloader/BODY -> completed download staging -> importer fixture boundary`.

This must run without public network access.

## Performance and Resource Gates

The live-NNTP PR must preserve the locked optimization budgets and add transport-specific evidence:

- header scanner uses bounded XOVER ranges and bounded Python memory;
- XOVER-to-`ArticleHeader` throughput is measured separately from network delay;
- BODY downloader retains direct-to-disk streaming behavior;
- connection count never exceeds per-provider `max_connections`;
- scanner/database work does not regress 100K header throughput below the existing 25,000 headers/sec gate;
- 1M PostgreSQL release search remains below 150 ms p95;
- normal read APIs remain below 100 ms p95;
- no credentials appear in benchmark reports or CI logs.

## Deployment Contract

Add runtime support for:

- `LOREX_DATABASE_URL` (existing);
- `LOREX_CREDENTIAL_KEY` (new, base64url 32-byte AES key).

TrueNAS/Docker documentation must instruct operators to generate and preserve the credential key before entering provider credentials. Losing the key makes stored provider credentials unrecoverable and requires re-entering them. Changing the key without re-encrypting existing credentials is intentionally rejected.

The application must never auto-generate a replacement key on startup because doing so could make existing ciphertext irrecoverable without warning.

## Initial Real-Provider Validation

After CI passes on the deterministic fake server, perform a manual authorized validation against the user's configured providers.

Validation sequence:

1. create provider records through the provider API/settings path;
2. verify connection/authentication;
3. select one audiobook group available from the provider;
4. scan a deliberately small XOVER range;
5. verify release/article persistence and checkpoint behavior;
6. grab one authorized/public-domain/test release;
7. confirm BODY streaming, provider health, and fallback behavior if a second provider is configured;
8. pass output to the existing import pipeline and verify the final managed-library result.

Real provider credentials must not be committed, pasted into test fixtures, or echoed into chat/log output.

## Out of Scope

This first live-NNTP integration does not include:

- Usenet posting/upload;
- plaintext or non-TLS providers;
- automatic credential-key rotation;
- OAuth/provider-specific web login flows;
- a broad redesign of LoreX Settings UI;
- changing the existing importer/media optimization architecture;
- multi-user credential ownership;
- storing the encryption master key in PostgreSQL.

## Merge Gates

The live-NNTP PR may merge only when:

1. all new behavior was developed red-green;
2. encryption and secret-redaction tests pass;
3. protocol/scanner/downloader fake-server integration tests pass;
4. PostgreSQL migrations pass from a clean database;
5. existing backend/frontend tests pass;
6. transport/resource benchmarks pass and locked PR1-PR8 performance gates are not regressed;
7. review finds no plaintext credential path or checkpoint/data-loss flaw;
8. CI is green on the exact head being merged.
