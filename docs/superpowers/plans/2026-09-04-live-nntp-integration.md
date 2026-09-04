# LoreX Live NNTP Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LoreX's mock Usenet boundary with encrypted PostgreSQL provider configuration, a real TLS NNTP client, restart-safe bounded header scanning, and streamed article downloads integrated with the existing downloader/import pipeline.

**Architecture:** Keep PostgreSQL authoritative and reuse the existing `IndexBatch`/checkpoint and `ProviderSet`/`StreamingDownloader` boundaries. Add a small synchronous TLS NNTP transport under `backend/lorex/nntp`, encrypt provider credentials with AES-256-GCM using a runtime-only `LOREX_CREDENTIAL_KEY`, and expose provider configuration through masked FastAPI endpoints. Long-running scanning runs outside request handlers through a bounded worker entry point.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL 16, `cryptography` AESGCM, Python `socket`/`ssl`, pytest, existing Redis/downloader/importer infrastructure.

**Spec:** `docs/superpowers/specs/2026-09-04-live-nntp-integration-design.md`

## Global Constraints

- Product version remains `0.1.1 alpha`; Python `0.1.1a1`; npm `0.1.1-alpha.1`.
- TLS is mandatory for NNTP providers in this implementation.
- Provider username/password ciphertext is stored in PostgreSQL; the 32-byte master key is never stored in PostgreSQL.
- `LOREX_CREDENTIAL_KEY` is a base64url-encoded 32-byte key and is never auto-generated at application startup.
- AES-256-GCM uses a random 96-bit nonce per encrypted field and AAD binding to provider ID plus field name.
- PostgreSQL remains authoritative for provider configuration and scan checkpoints.
- Header ranges are bounded; full article BODY payloads are streamed and never intentionally buffered whole in Python memory.
- Existing provider ordering/fill fallback and downloader concurrency limits remain authoritative.
- No real provider secrets appear in source, tests, CI, logs, benchmark output, or PR text.
- Existing optimization gates remain: >=25,000 headers/sec at 100K, PostgreSQL 1M search p95 <150 ms, normal read API p95 <100 ms.
- All behavior-changing work follows red-green TDD and exact-head CI verification before merge.

---

### Task 1: Credential Envelope and Runtime Master Key

**Files:**
- Modify: `pyproject.toml`
- Create: `backend/lorex/security/__init__.py`
- Create: `backend/lorex/security/credentials.py`
- Create: `tests/test_provider_credentials.py`

**Interfaces:**
- Produces: `CredentialCipher.from_base64url(value: str) -> CredentialCipher`
- Produces: `CredentialCipher.encrypt(provider_id: str, field_name: str, plaintext: str) -> str`
- Produces: `CredentialCipher.decrypt(provider_id: str, field_name: str, envelope: str) -> str`
- Produces: `credential_cipher_from_env(environ: Mapping[str, str] = os.environ) -> CredentialCipher | None`

- [ ] **Step 1: Write failing credential-envelope tests**

```python
from base64 import urlsafe_b64encode
import pytest

from lorex.security.credentials import CredentialCipher, CredentialError


def _key(byte: int = 7) -> str:
    return urlsafe_b64encode(bytes([byte]) * 32).decode().rstrip("=")


def test_envelope_is_not_plaintext_and_round_trips():
    cipher = CredentialCipher.from_base64url(_key())
    value = cipher.encrypt("provider-1", "password", "secret-pass")
    assert "secret-pass" not in value
    assert value.startswith("v1.")
    assert cipher.decrypt("provider-1", "password", value) == "secret-pass"


def test_wrong_provider_aad_fails_closed():
    cipher = CredentialCipher.from_base64url(_key())
    value = cipher.encrypt("provider-1", "password", "secret-pass")
    with pytest.raises(CredentialError):
        cipher.decrypt("provider-2", "password", value)


def test_wrong_key_fails_closed():
    value = CredentialCipher.from_base64url(_key(7)).encrypt("p", "username", "user")
    with pytest.raises(CredentialError):
        CredentialCipher.from_base64url(_key(8)).decrypt("p", "username", value)
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/test_provider_credentials.py -q`

Expected: import failure because `lorex.security.credentials` does not exist.

- [ ] **Step 3: Add the crypto dependency and minimal implementation**

Add to `pyproject.toml` dependencies:

```toml
"cryptography>=45,<46",
```

Implement `CredentialCipher` with `cryptography.hazmat.primitives.ciphers.aead.AESGCM`, `secrets.token_bytes(12)`, URL-safe base64 without required padding, and envelope format:

```text
v1.<nonce_b64url>.<ciphertext_and_tag_b64url>
```

AAD must be exactly UTF-8 bytes of:

```text
lorex:nntp-provider:<provider_id>:<field_name>:v1
```

`CredentialError` must replace underlying InvalidTag/base64/value exceptions without including secret material.

- [ ] **Step 4: Add environment-key validation tests**

Cover missing key -> `None`, malformed base64 -> `CredentialError`, decoded lengths other than 32 -> `CredentialError`, valid key -> cipher.

- [ ] **Step 5: Run focused and full backend tests**

Run:

```bash
pytest tests/test_provider_credentials.py -q
pytest -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml backend/lorex/security tests/test_provider_credentials.py
git commit -m "feat: add encrypted provider credential envelopes"
```

---

### Task 2: Durable Provider and Group Configuration

**Files:**
- Create: `migrations/versions/0006_live_nntp_providers.py`
- Modify: `backend/lorex/db_models.py`
- Create: `backend/lorex/nntp/__init__.py`
- Create: `backend/lorex/nntp/models.py`
- Create: `backend/lorex/nntp/repository.py`
- Create: `tests/test_postgres_nntp_providers.py`

**Interfaces:**
- Produces: `NntpProvider`, `NntpProviderGroup`, `ProviderSecretUpdate`
- Produces: `PostgresNntpProviderRepository.create(...)`, `.get(id)`, `.list_enabled()`, `.list_all()`, `.update(...)`, `.delete(id)`
- Provider IDs are stable 32-character hex IDs and are the `IndexCheckpoint.source` value.

- [ ] **Step 1: Write failing PostgreSQL provider repository tests**

Tests must assert:

```python
saved = repo.create(
    name="Primary",
    host="news.example.test",
    port=563,
    enabled=True,
    priority=10,
    fill_server=False,
    max_connections=8,
    username="alice",
    password="p@ss",
    groups=[NntpProviderGroup(group_name="alt.binaries.audiobooks", scan_batch_size=5000)],
)
row = raw_session.get(NntpProviderRow, saved.id)
assert row.username_encrypted != "alice"
assert row.password_encrypted != "p@ss"
assert repo.get(saved.id).username == "alice"
assert repo.get(saved.id).password == "p@ss"
```

Also assert unique provider names, normalized group comparison, update-without-secret preserves ciphertext, explicit clear removes ciphertext, and delete removes child groups.

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/test_postgres_nntp_providers.py -q`

Expected: missing models/repository/migration types.

- [ ] **Step 3: Add migration `0006_live_nntp_providers`**

Create `nntp_providers` with:

```text
id VARCHAR(32) PK
name VARCHAR(128) UNIQUE NOT NULL
host TEXT NOT NULL
port INTEGER NOT NULL
enabled BOOLEAN NOT NULL DEFAULT true
priority INTEGER NOT NULL DEFAULT 100
fill_server BOOLEAN NOT NULL DEFAULT false
max_connections INTEGER NOT NULL DEFAULT 4
username_encrypted TEXT NULL
password_encrypted TEXT NULL
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
```

Create `nntp_provider_groups` with composite PK `(provider_id, group_name_normalized)`, FK cascade to providers, display `group_name`, `enabled`, `scan_batch_size`, and integer `backfill_days`. Use `down_revision = "0005_library_read_indexes"`.

Enforce application validation `1 <= port <= 65535`, `1 <= max_connections <= 64`, `100 <= scan_batch_size <= 50_000`, and `0 <= backfill_days <= 10_000`.

- [ ] **Step 4: Add ORM/domain/repository implementation**

Repository accepts a `CredentialCipher`; encryption/decryption occurs only there. Returned domain objects may carry plaintext credentials for immediate runtime use, but their `repr` must not expose them: mark secret dataclass fields `repr=False`.

- [ ] **Step 5: Verify migrations and repository behavior**

Run:

```bash
alembic upgrade head
pytest tests/test_postgres_nntp_providers.py -q
pytest -q
```

Expected: migration chain `0001 -> ... -> 0006` and all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/0006_live_nntp_providers.py backend/lorex/db_models.py backend/lorex/nntp tests/test_postgres_nntp_providers.py
git commit -m "feat: persist encrypted NNTP provider configuration"
```

---

### Task 3: Masked Provider Configuration API

**Files:**
- Create: `backend/lorex/api/nntp_settings.py`
- Modify: `backend/lorex/main.py`
- Create: `tests/test_nntp_provider_api.py`

**Interfaces:**
- Produces endpoints under `/api/settings/nntp/providers`
- `GET /` returns masked state only
- `POST /` creates a provider
- `PATCH /{provider_id}` updates provider fields/secrets
- `DELETE /{provider_id}` deletes an unused provider
- `POST /{provider_id}/credentials/{field}/clear` clears `username` or `password`
- Connection test endpoint is added in Task 4 after the transport exists.

- [ ] **Step 1: Write RED API tests**

Example response contract:

```python
response = client.get("/api/settings/nntp/providers")
item = response.json()[0]
assert item["name"] == "Primary"
assert item["username_configured"] is True
assert item["password_configured"] is True
assert "username" not in item
assert "password" not in item
assert "username_encrypted" not in item
assert "password_encrypted" not in item
```

Also test create/update validation and that omitted credentials preserve existing encrypted secrets.

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_nntp_provider_api.py -q`

Expected: 404/missing router.

- [ ] **Step 3: Implement Pydantic request/response models and router**

Use explicit response models. Never serialize provider domain objects with `asdict()` because they contain plaintext runtime fields.

- [ ] **Step 4: Wire repository and cipher into `AppContainer`**

When PostgreSQL is configured, create `PostgresNntpProviderRepository` if `LOREX_CREDENTIAL_KEY` is valid. If the key is absent, keep the app bootable and provider reads masked; writes/tests requiring encryption/decryption return a clear 503 configuration error.

- [ ] **Step 5: Run focused/full tests and commit**

```bash
pytest tests/test_nntp_provider_api.py -q
pytest -q
git add backend/lorex/api/nntp_settings.py backend/lorex/main.py tests/test_nntp_provider_api.py
git commit -m "feat: add masked NNTP provider settings API"
```

---

### Task 4: LoreX TLS NNTP Protocol Client and Fake Server

**Files:**
- Create: `backend/lorex/nntp/errors.py`
- Create: `backend/lorex/nntp/protocol.py`
- Create: `backend/lorex/nntp/client.py`
- Create: `tests/support/fake_nntp.py`
- Create: `tests/test_nntp_client.py`
- Modify: `backend/lorex/api/nntp_settings.py`

**Interfaces:**
- Produces: `NntpClient.connect()`, `.authenticate(username, password)`, `.group(name) -> GroupInfo`, `.xover(start, end) -> Iterator[OverviewRecord]`, `.body(message_id) -> Iterator[bytes]`, `.quit()`
- Produces: `NntpAuthenticationError`, `NntpTemporaryError`, `NntpArticleMissing`, `NntpProtocolError`, `NntpConfigurationError`
- Transport limits: max line length 64 KiB; connect/read timeout defaults 30 s; BODY chunks max 64 KiB.

- [ ] **Step 1: Write fake-server-backed RED tests**

Required cases:

```text
valid TLS greeting
certificate rejection with untrusted CA
AUTHINFO USER/PASS success
AUTHINFO rejection without secret echo
GROUP response parsing
XOVER range + multiline termination
XOVER dot unstuffing
BODY streaming without whole-payload return
BODY 430 -> NntpArticleMissing
temporary 4xx/network drop -> NntpTemporaryError
oversize line -> NntpProtocolError
read timeout -> NntpTemporaryError
```

The fake server uses a test-only CA/certificate generated for the test process or committed as non-secret test certificate material; the production client trusts the system context unless a test context is injected.

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_nntp_client.py -q`

Expected: missing client/protocol modules.

- [ ] **Step 3: Implement the line protocol parser**

Commands are ASCII terminated with CRLF. Reject CR/LF in command arguments. Multiline reader stops only on line `b".\r\n"`; a line beginning `b".."` loses one leading dot.

For BODY, yield data incrementally and restore CRLF between protocol lines so downstream yEnc/decoded processing can consume exact logical article data without holding the whole response.

- [ ] **Step 4: Implement `NntpClient` connection/auth/group/xover/body**

Use `socket.create_connection`, `ssl.create_default_context`, hostname verification, and injected `SSLContext` only for tests. Implement XOVER directly; if a server rejects XOVER with unsupported-command response, try `OVER` exactly once and cache that command choice for the client instance.

- [ ] **Step 5: Add provider connection-test endpoint**

`POST /api/settings/nntp/providers/{id}/test` loads/decrypts the provider, connects, authenticates, quits, and returns only:

```json
{"ok": true, "authenticated": true}
```

On failure return a sanitized category/message; do not return raw NNTP server text.

- [ ] **Step 6: Verify and commit**

```bash
pytest tests/test_nntp_client.py tests/test_nntp_provider_api.py -q
pytest -q
git add backend/lorex/nntp backend/lorex/api/nntp_settings.py tests/support/fake_nntp.py tests/test_nntp_client.py tests/test_nntp_provider_api.py
git commit -m "feat: add TLS NNTP protocol client"
```

---

### Task 5: Bounded Live/Backfill Header Scanner

**Files:**
- Create: `backend/lorex/nntp/scanner.py`
- Create: `backend/lorex/services/nntp_scanning.py`
- Create: `tests/test_nntp_scanner.py`

**Interfaces:**
- Produces: `ScanMode = Literal["live", "backfill"]`
- Produces: `scan_provider_group_once(provider, group, release_repository, client_factory, mode) -> ScanStats`
- Produces: `ScanStats(headers_received, malformed_rows, batches_committed, checkpoint_article, duration_ms)`

- [ ] **Step 1: Write RED scanner tests**

Lock checkpoint semantics with cases:

```text
checkpoint 100 + fully received XOVER 101-200 -> checkpoint 200
sparse rows 101,105,199 with full range response -> checkpoint 200
malformed rows inside a complete range -> checkpoint 200 and malformed counter increments
connection drop before terminator -> checkpoint remains 100
DB commit failure -> checkpoint remains 100
provider rename with same provider ID -> resumes from 101
checkpoint above server high -> no backward movement
```

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_nntp_scanner.py -q`

- [ ] **Step 3: Implement deterministic range selection**

Live mode begins at `max(server_low, checkpoint + 1)` and moves toward `server_high` in `scan_batch_size` ranges.

When no checkpoint exists, live mode starts at `max(server_low, server_high - scan_batch_size + 1)` to avoid accidental full-retention ingestion on first startup.

Backfill mode walks backward from the oldest known live boundary but remains bounded by `backfill_days` policy and server low watermark. Persist a separate checkpoint source suffix `:<mode>` only if needed to avoid live/backfill collision; otherwise use a dedicated scanner-state row. Pick one representation in implementation and test it explicitly before adding code that depends on it.

- [ ] **Step 4: Feed complete ranges to existing `index_batches`**

Construct:

```python
IndexBatch(
    headers=headers,
    checkpoint=IndexCheckpoint(source=provider.id, group=group.group_name, article_number=range_end),
)
```

Only call `index_batches` after the XOVER multiline terminator was received. This allows sparse/malformed rows to advance across a fully observed range without advancing across a partial network response.

- [ ] **Step 5: Verify and commit**

```bash
pytest tests/test_nntp_scanner.py tests/test_streaming_indexer.py -q
pytest -q
git add backend/lorex/nntp/scanner.py backend/lorex/services/nntp_scanning.py tests/test_nntp_scanner.py
git commit -m "feat: add restart-safe NNTP header scanning"
```

---

### Task 6: Real Article Provider and Existing Downloader Integration

**Files:**
- Create: `backend/lorex/nntp/article_provider.py`
- Modify: `backend/lorex/downloader/provider.py`
- Create: `tests/test_nntp_article_provider.py`
- Modify: `tests/test_streaming_downloader.py` or the current downloader test file used by PR5

**Interfaces:**
- Produces: `NntpArticleProvider.stream_article(message_id: str) -> Iterator[bytes]`
- Consumes existing: `ProviderSet`, `ProviderPool`, `ArticleUnavailable`, `ProviderTemporaryError`

- [ ] **Step 1: Write RED adapter tests**

Assert:

```text
BODY success yields bounded byte chunks
430/missing article maps to ArticleUnavailable
network/transient server error maps to ProviderTemporaryError
auth/config errors do not masquerade as missing articles
primary missing article falls through to fill provider
per-provider ProviderPool max_connections is still honored
large BODY fixture peak Python allocation remains bounded
```

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_nntp_article_provider.py -q`

- [ ] **Step 3: Implement adapter without duplicating fallback**

`NntpArticleProvider` owns one provider's connection creation/auth/BODY mapping only. `ProviderSet` remains the only cross-provider fallback layer.

- [ ] **Step 4: Verify downstream streaming downloader**

Run:

```bash
pytest tests/test_nntp_article_provider.py -q
pytest -q
```

Confirm the existing direct-to-disk article files remain the sink and no whole BODY is assembled first.

- [ ] **Step 5: Commit**

```bash
git add backend/lorex/nntp/article_provider.py backend/lorex/downloader/provider.py tests/test_nntp_article_provider.py tests
git commit -m "feat: stream real NNTP article bodies"
```

---

### Task 7: Production Provider Factory, Download Wiring, and Scanner Worker

**Files:**
- Create: `backend/lorex/nntp/factory.py`
- Create: `backend/lorex/workers/__init__.py`
- Create: `backend/lorex/workers/nntp_scanner.py`
- Modify: `backend/lorex/main.py`
- Modify: `backend/lorex/api/releases.py`
- Modify: `docker-compose.yml`
- Create: `tests/test_live_nntp_wiring.py`

**Interfaces:**
- Produces: `build_provider_set(provider_repository) -> ProviderSet`
- Produces worker CLI module: `python -m lorex.workers.nntp_scanner --once --mode live`
- Production PostgreSQL download path consumes persisted release article rows and `StreamingDownloader.download_job(...)`.

- [ ] **Step 1: Write RED wiring tests**

Cases:

```text
no providers: app boots; provider-required download returns explicit configuration error
providers configured + key present: provider factory creates live ProviderSet
providers configured + key missing: app boots; live provider operation fails locally without remote-health penalty
process-next resolves persisted articles and calls StreamingDownloader, not MockDownloader
scanner worker --once processes one bounded provider/group iteration and exits 0
```

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_live_nntp_wiring.py -q`

- [ ] **Step 3: Implement provider factory and live downloader selection**

Use enabled provider rows only. Map domain config into existing `ProviderConfig(name, host, port, priority, fill_server, max_connections, enabled=True, tls=True)` and clients keyed by provider name.

Do not silently fall back to `MockDownloader` in PostgreSQL production mode. Mock components remain explicit test/development fixtures only.

- [ ] **Step 4: Replace legacy `/downloads/process-next` mock-success path**

For PostgreSQL/live mode:

```python
articles = container.releases.get_articles(release.id)
result = container.downloader.download_job(job, release, articles)
```

Then hand the completed result into the existing durable import path rather than claiming completion before import state is persisted.

- [ ] **Step 5: Add scanner worker and Compose service**

Add `scanner` service using the same image and volumes as `api`, command:

```yaml
command: ["python", "-m", "lorex.workers.nntp_scanner"]
```

Pass `LOREX_DATABASE_URL`, `LOREX_REDIS_URL`, and `LOREX_CREDENTIAL_KEY` through runtime configuration. The repository must not contain an actual key value.

- [ ] **Step 6: Verify and commit**

```bash
pytest tests/test_live_nntp_wiring.py -q
pytest -q
git add backend/lorex/nntp/factory.py backend/lorex/workers backend/lorex/main.py backend/lorex/api/releases.py docker-compose.yml tests/test_live_nntp_wiring.py
git commit -m "feat: wire live NNTP into LoreX workers"
```

---

### Task 8: Deterministic End-to-End Live Protocol Fixture

**Files:**
- Create: `tests/test_live_nntp_end_to_end.py`
- Modify only production files if a RED failure exposes a missing production boundary; do not weaken assertions.

**Interfaces:**
- Exercises: fake TLS NNTP -> XOVER -> `ArticleHeader` -> `index_batches` -> PostgreSQL release/articles -> grab -> `StreamingDownloader`/BODY -> download staging -> importer boundary.

- [ ] **Step 1: Write the complete RED integration test**

Use a fake release whose overview subjects form one valid audiobook candidate and whose BODY responses contain deterministic test payloads. Assert:

```python
assert release_repo.search_page(...).total == 1
assert len(release_repo.get_articles(release.id)) > 0
assert checkpoint.article_number == requested_range_end
assert downloaded_file.exists()
assert downloaded_file.read_bytes() == expected_payload
assert no_secret_text_in(caplog.text)
```

Also include a second provider where one article is missing on primary and succeeds on fill.

- [ ] **Step 2: Run RED and diagnose only the observed missing boundary**

Run: `pytest tests/test_live_nntp_end_to_end.py -q`

- [ ] **Step 3: Make the minimum production corrections needed**

Do not replace real protocol/scanner/downloader calls with mocks inside this test. Only the network server itself is fake/local.

- [ ] **Step 4: Verify the full backend suite**

Run:

```bash
pytest tests/test_live_nntp_end_to_end.py -q
pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_live_nntp_end_to_end.py backend/lorex
git commit -m "test: prove live NNTP end-to-end flow"
```

---

### Task 9: Transport Benchmarks, Secret-Scan Gates, CI, and Deployment Docs

**Files:**
- Create: `benchmarks/live_nntp_scenarios.py`
- Create: `benchmarks/run_live_nntp.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Create: `docs/performance/live-nntp-integration.md`
- Create: `tests/test_no_nntp_secret_leaks.py`

**Interfaces:**
- Benchmark output: `benchmark-results/live-nntp.json`, `benchmark-results/live-nntp.md`
- CI must run migrations, all correctness tests, existing PR1/6/7/8 benchmarks, and new live-NNTP gates.

- [ ] **Step 1: Write RED benchmark/security gate tests**

Require:

```text
10K synthetic overview rows parse with bounded memory
64 MiB BODY fixture streams with bounded Python allocation
provider connection concurrency never exceeds configured max_connections
100K existing header throughput remains >=25,000 headers/sec
1M search remains <150 ms p95
normal read API remains <100 ms p95
known fake username/password strings do not occur in captured logs, JSON reports, markdown reports, or provider API reads
```

- [ ] **Step 2: Run RED**

Run:

```bash
pytest tests/test_no_nntp_secret_leaks.py -q
python -m benchmarks.run_live_nntp --output benchmark-results
```

Expected: missing benchmark runner/security coverage.

- [ ] **Step 3: Implement benchmark runner and CI integration**

Add `LOREX_CREDENTIAL_KEY` to CI as a deterministic fake test key only, for example generated at job runtime from 32 non-secret test bytes. Do not add a repository secret or production value.

Append `python -m benchmarks.run_live_nntp --output benchmark-results` after existing benchmark suites and append its markdown to `$GITHUB_STEP_SUMMARY`.

- [ ] **Step 4: Document deployment/key handling**

README must state:

```text
Generate one 32-byte random credential key before entering provider credentials.
Store it as the TrueNAS/container secret LOREX_CREDENTIAL_KEY.
Back it up separately from PostgreSQL.
Losing the key requires re-entering provider credentials.
Never place the key in docker-compose.yml or source control.
```

Document provider creation/test flow without real usernames/passwords.

- [ ] **Step 5: Run full exact-branch verification**

Run equivalents in CI:

```bash
alembic upgrade head
pytest -q
npm --prefix frontend install
npm --prefix frontend run build
python -m benchmarks.run_baseline --profile ci --output benchmark-results --frontend-dist frontend/dist
python -m benchmarks.run_pr6 --output benchmark-results
python -m benchmarks.run_pr7 --output benchmark-results
python -m benchmarks.run_pr8 --output benchmark-results --frontend-dist frontend/dist
python -m benchmarks.run_live_nntp --output benchmark-results
```

All hard gates must pass before the PR becomes eligible for merge.

- [ ] **Step 6: Record measured evidence and commit**

Populate `docs/performance/live-nntp-integration.md` only with fresh measured values from the implementation head; include CPU/memory/network-fixture caveats and the exact commit/run identifiers.

```bash
git add benchmarks .github/workflows/ci.yml README.md docs/performance/live-nntp-integration.md tests/test_no_nntp_secret_leaks.py
git commit -m "perf: verify live NNTP integration"
```

---

### Task 10: PR Review and Exact-Head Merge Gate

**Files:**
- No production changes unless review or CI finds a concrete defect.

**Interfaces:**
- Final integration branch: `feature/live-nntp-integration`
- Merge target: `main`
- Merge method: squash with exact expected head SHA.

- [ ] **Step 1: Open draft PR after the first RED/green implementation slice exists**

Title:

```text
Live NNTP integration with encrypted provider credentials
```

Body must summarize security model, protocol scope, scan checkpoint semantics, downloader reuse, fake-server test coverage, and measured evidence. Never include credentials.

- [ ] **Step 2: Review for correctness/security**

Inspect all changed files and explicitly check:

```text
no plaintext credential persistence/logging/API serialization
no master key persistence in PostgreSQL
AES-GCM AAD binds provider+field
no TLS verification bypass in production config
no CR/LF command injection
no partial-XOVER checkpoint advancement
no whole-BODY buffering
no duplicated provider fallback logic
no silent mock-download production path
```

- [ ] **Step 3: Resolve all review findings with red-green tests**

Every production bug found in review gets a failing regression test before the fix.

- [ ] **Step 4: Run fresh exact-head CI**

Do not merge based on an earlier green commit. Confirm backend, frontend, migrations, baseline benchmarks, live-NNTP benchmarks, and artifact publication all succeeded on the exact PR head.

- [ ] **Step 5: Merge with expected head SHA**

Use squash merge only after the exact-head gate is green and review threads/comments are clear. Record merged state, `merged_at`, and merge commit SHA.
