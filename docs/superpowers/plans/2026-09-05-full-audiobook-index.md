# Full Audiobook History Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LoreX continuously index every audiobook release available in enabled NNTP audiobook groups while keeping live ingestion current and controlling database growth.

**Architecture:** Keep the existing single scanner worker and forward live checkpoint. Add a separate durable descending historical cursor that runs only when live work is not due. Normalize new article persistence through one payload row per physical filename/group so millions of segments do not repeat verbose subject/group strings.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, PostgreSQL 16, Alembic, pytest, React/TypeScript/Vite.

**Spec:** `docs/superpowers/specs/2026-09-05-full-audiobook-index-design.md`

## Global Constraints

- Live scanning always has priority over historical crawling.
- Full history defaults enabled for every enabled provider group after migration.
- No NNTP BODY request is allowed during indexing.
- Rejected overview headers are never persisted.
- Historical state is persisted only after the fetched window has been indexed successfully.
- Existing encrypted provider credentials and `LOREX_CREDENTIAL_KEY` behavior are unchanged.
- Existing release/article rows remain readable and downloadable after migration.
- Existing PostgreSQL volumes are upgraded in place; no volume reset is required.
- CI must pass backend, frontend, packaging, and benchmark gates before merge.

---

### Task 1: Compact persisted NNTP article metadata

**Files:**
- Create: `tests/test_compact_release_articles.py`
- Create: `migrations/versions/0008_compact_release_articles.py`
- Modify: `backend/lorex/db_models.py`
- Modify: `backend/lorex/indexer/grouping.py`
- Modify: `backend/lorex/postgres_repository.py`

**Interfaces:**
- Produces: `payload_filename(subject: str) -> str` in `lorex.indexer.grouping`.
- Produces: `ReleasePayloadRow` and nullable `ReleaseArticleRow.payload_id`.
- Preserves: `PostgresReleaseRepository.get_articles(release_id) -> tuple[ArticleHeader, ...]`.

- [ ] **Step 1: Write the failing compact-persistence tests**

```python

def test_compact_rows_deduplicate_payload_filename(postgres_releases, db_session):
    release = audiobook_release("release-1", "Book.archive")
    articles = (
        ArticleHeader("<1@test>", 'post "Book.part01.rar" yEnc (1/2)', 100, "alt.binaries.audiobooks"),
        ArticleHeader("<2@test>", 'post "Book.part01.rar" yEnc (2/2)', 100, "alt.binaries.audiobooks"),
    )
    postgres_releases.commit_index_batch([(release, articles)])

    payloads = db_session.execute(select(ReleasePayloadRow)).scalars().all()
    rows = db_session.execute(select(ReleaseArticleRow).order_by(ReleaseArticleRow.id)).scalars().all()

    assert [(item.filename, item.group) for item in payloads] == [("Book.part01.rar", "alt.binaries.audiobooks")]
    assert all(row.payload_id == payloads[0].id for row in rows)
    assert all(row.subject is None and row.group is None for row in rows)


def test_get_articles_reconstructs_compact_and_legacy_rows(postgres_releases, db_session):
    # Insert one compact row through the repository and one legacy row directly.
    # Both reads must return usable message id, bytes, filename-bearing subject and group.
    ...
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run: `pytest -q tests/test_compact_release_articles.py`

Expected: FAIL because `ReleasePayloadRow`, `payload_id`, and compact persistence do not exist.

- [ ] **Step 3: Add the additive migration**

Create `0008_compact_release_articles.py` with:

```python
revision = "0008_compact_release_articles"
down_revision = "0007_runtime_orchestration"


def upgrade() -> None:
    op.create_table(
        "release_payloads",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("release_id", sa.String(length=64), sa.ForeignKey("releases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("group", sa.Text(), nullable=False),
        sa.UniqueConstraint("release_id", "filename", "group", name="ux_release_payloads_release_file_group"),
    )
    op.create_index("ix_release_payloads_release_id", "release_payloads", ["release_id"])
    op.add_column("release_articles", sa.Column("payload_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_release_articles_payload_id",
        "release_articles",
        "release_payloads",
        ["payload_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("release_articles", "subject", existing_type=sa.Text(), nullable=True)
    op.alter_column("release_articles", "group", existing_type=sa.Text(), nullable=True)
```

Downgrade reverses the additive objects only when legacy columns can remain nullable; do not attempt a lossy backfill from payload rows into old verbose subjects.

- [ ] **Step 4: Add payload filename normalization**

In `grouping.py`, expose a helper that returns the quoted yEnc filename when present and otherwise returns the normalized filename-bearing subject:

```python

def payload_filename(subject: str) -> str:
    stripped = subject.rstrip()
    yenc = _YENC_QUOTED_RE.search(stripped)
    if yenc is not None:
        return yenc.group("filename").strip()
    return normalize_subject(subject).strip() or "payload.bin"
```

- [ ] **Step 5: Persist compact rows and preserve legacy reads**

Update `commit_index_batch()` so inserted releases first create distinct payload rows keyed by `(release_id, payload_filename(article.subject), article.group)`. New `release_articles` rows contain `release_id`, `payload_id`, `message_id`, and `bytes`; `subject` and `group` are null.

Update `get_articles()` to outer-join payload rows and return:

```python
subject = row.subject if row.subject else f'"{payload.filename}"'
group = row.group if row.group else payload.group
```

Legacy rows with null `payload_id` must follow the old path unchanged.

- [ ] **Step 6: Run compact persistence and existing download/NZB tests**

Run:

```bash
pytest -q tests/test_compact_release_articles.py tests/test_nzb.py tests/test_postprocess.py tests/test_download_worker.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/lorex/db_models.py backend/lorex/indexer/grouping.py backend/lorex/postgres_repository.py migrations/versions/0008_compact_release_articles.py tests/test_compact_release_articles.py
git commit -m "feat: compact persisted NNTP article metadata"
```

---

### Task 2: Add durable full-history state and descending range selection

**Files:**
- Create: `tests/test_nntp_full_history.py`
- Create: `migrations/versions/0009_full_history_state.py`
- Modify: `backend/lorex/db_models.py`
- Modify: `backend/lorex/nntp/models.py`
- Modify: `backend/lorex/nntp/repository.py`
- Modify: `backend/lorex/runtime_repository.py`
- Modify: `backend/lorex/nntp/scanner.py`
- Modify: `backend/lorex/services/nntp_scanning.py`

**Interfaces:**
- Produces: `BackfillGroupState` runtime dataclass.
- Produces: `scan_group_backfill_once(provider, group, release_repository, runtime_repository, ...) -> ScanStats`.
- Produces: `NntpProviderGroup.backfill_enabled: bool = True`.

- [ ] **Step 1: Write RED tests for descending historical windows**

```python

def test_full_history_starts_at_high_and_moves_backward():
    # GROUP low=100 high=109, batch=4.
    # First request must be XOVER 106-109 and persist next_high=105.
    ...


def test_full_history_completes_at_current_low_water_mark():
    # next_high=102 with GROUP low=100 -> request 100-102, then status complete.
    ...


def test_full_history_cursor_is_independent_from_live_checkpoint():
    # Live checkpoint remains forward-only and unchanged by descending history.
    ...


def test_failed_history_batch_does_not_advance_cursor():
    ...
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest -q tests/test_nntp_full_history.py`

Expected: FAIL because historical state and descending scan function are missing.

- [ ] **Step 3: Add migration and ORM state**

`0009_full_history_state.py` adds `backfill_enabled BOOLEAN NOT NULL DEFAULT true` to `nntp_provider_groups` and creates `indexer_backfill_state` with the fields in the design spec.

- [ ] **Step 4: Add provider-group compatibility**

Extend `NntpProviderGroup`:

```python
backfill_enabled: bool = True
```

Update `PostgresNntpProviderRepository` row/domain mappings and create/update persistence to read/write it. Retain `backfill_days` in storage and API compatibility.

- [ ] **Step 5: Add runtime state methods**

Add methods with exact behavior:

```python
get_backfill_state(provider_id: str, group_name: str) -> BackfillGroupState | None
mark_backfill_started(provider_id: str, group_name: str, *, current_low: int, current_high: int) -> BackfillGroupState
advance_backfill(provider_id: str, group_name: str, *, next_high: int, headers_delta: int, releases_delta: int, current_low: int) -> BackfillGroupState
mark_backfill_error(provider_id: str, group_name: str, error: str) -> None
backfill_states() -> tuple[BackfillGroupState, ...]
```

Initialization must preserve the first observed `initial_low`/`initial_high`; `advance_backfill` marks complete when `next_high < current_low`.

- [ ] **Step 6: Add descending scan function**

Implement `scan_group_backfill_once()` separately from the live `_scan_range()` so the live monotonic checkpoint invariant remains untouched. It must authenticate and call `GROUP` exactly like live scanning, fetch one descending window, pass rows to `index_batches()` with **no live checkpoint**, and advance historical state only after indexing returns successfully.

- [ ] **Step 7: Run targeted and existing scanner tests**

Run:

```bash
pytest -q tests/test_nntp_full_history.py tests/test_nntp_scanner.py tests/test_nntp_live_scanner.py tests/test_indexer_checkpoint.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/lorex/db_models.py backend/lorex/nntp/models.py backend/lorex/nntp/repository.py backend/lorex/runtime_repository.py backend/lorex/nntp/scanner.py backend/lorex/services/nntp_scanning.py migrations/versions/0009_full_history_state.py tests/test_nntp_full_history.py
git commit -m "feat: add resumable full-history NNTP cursor"
```

---

### Task 3: Schedule history continuously without delaying live scans

**Files:**
- Create: `tests/test_scanner_full_history_scheduler.py`
- Modify: `backend/lorex/workers/nntp_scanner.py`

**Interfaces:**
- Preserves: continuous heartbeat thread from PR #23.
- Produces: one-history-batch-at-a-time scheduler with live priority.

- [ ] **Step 1: Write RED scheduler tests**

```python

def test_due_live_scan_runs_before_history_step():
    events = []
    run_forever(..., live_scan_fn=lambda *a, **k: events.append("live"), backfill_scan_fn=lambda *a, **k: events.append("history"), ...)
    assert events[0] == "live"


def test_history_runs_between_live_intervals():
    ...


def test_disabled_full_history_group_is_skipped():
    ...


def test_history_progress_resumes_from_repository_state_after_worker_restart():
    ...
```

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_scanner_full_history_scheduler.py`

Expected: FAIL because the worker has no backfill lane.

- [ ] **Step 3: Implement a round-robin historical step**

Keep `run_pass(..., mode="live")` for current work. Add a helper that selects the next enabled provider/group with `backfill_enabled=True` and non-complete state, processes exactly one window, and advances the round-robin cursor. Do not run an unbounded history loop inside one scheduler iteration.

- [ ] **Step 4: Preserve live priority and heartbeat**

In `run_forever()`:

```python
if settings.enabled and (due or manually_requested):
    run_pass(..., mode="live")
    last_scan_at = monotonic()
    ...
else:
    run_backfill_step(...)
```

The independent heartbeat thread remains active during both lanes.

- [ ] **Step 5: Run worker tests**

Run:

```bash
pytest -q tests/test_scanner_full_history_scheduler.py tests/test_scanner_heartbeat.py tests/test_scanner_heartbeat_long_scan.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/lorex/workers/nntp_scanner.py tests/test_scanner_full_history_scheduler.py
git commit -m "feat: crawl history between live NNTP scans"
```

---

### Task 4: Expose full-history settings and progress through the API

**Files:**
- Create: `tests/test_indexer_full_history_api.py`
- Modify: `backend/lorex/api/nntp_settings.py`
- Modify: `backend/lorex/api/indexer.py`

**Interfaces:**
- Provider payload/response field: `backfill_enabled: bool`.
- Indexer group status fields: `backfill_status`, `backfill_initial_low`, `backfill_initial_high`, `backfill_next_high`, `backfill_headers_scanned`, `backfill_releases_indexed`, `backfill_percent`.

- [ ] **Step 1: Write RED API tests**

```python

def test_provider_groups_default_full_history_enabled(client):
    ...
    assert body["groups"][0]["backfill_enabled"] is True


def test_indexer_status_reports_history_progress(client, runtime):
    ...
    assert group["backfill_status"] == "scanning"
    assert group["backfill_percent"] == 50.0
```

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_indexer_full_history_api.py`

- [ ] **Step 3: Extend provider API models**

Add `backfill_enabled: bool = True` to `ProviderGroupInput` and `backfill_enabled: bool` to `ProviderGroupResponse`.

- [ ] **Step 4: Extend Indexer status**

Merge `runtime.backfill_states()` by `(provider_id, group_name.casefold())`. Calculate percent from the initial range and current `next_high`, clamped to `0..100`; completed state reports `100.0`.

- [ ] **Step 5: Run API suite**

Run:

```bash
pytest -q tests/test_indexer_full_history_api.py tests/test_indexer_runtime_api.py tests/test_nntp_settings_api.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/lorex/api/nntp_settings.py backend/lorex/api/indexer.py tests/test_indexer_full_history_api.py
git commit -m "feat: expose full-history indexing status"
```

---

### Task 5: Add Full history controls and progress to the React UI

**Files:**
- Create/Modify tests under: `frontend/src/**/*.test.tsx` according to existing frontend test placement.
- Modify: `frontend/src/components/ProviderEditor.tsx`
- Modify: `frontend/src/routes/SettingsPage.tsx`
- Modify: `frontend/src/routes/IndexerPage.tsx`
- Modify CSS only if existing classes cannot express the progress row.

**Interfaces:**
- `ProviderGroup.backfill_enabled: boolean`.
- Indexer status consumes Task 4 fields exactly.

- [ ] **Step 1: Write RED component tests**

Test that a new provider group renders `Full history` checked, editing preserves the value, and Indexer displays a 50% historical state from API data.

- [ ] **Step 2: Run frontend tests and verify RED**

Run: `cd frontend && npm test -- --run`

- [ ] **Step 3: Replace Backfill days with Full history**

Change the default group to:

```ts
const defaultGroup: ProviderGroup = {
  group_name: 'alt.binaries.audiobooks',
  enabled: true,
  scan_batch_size: 5000,
  backfill_days: 0,
  backfill_enabled: true,
}
```

Render:

```tsx
<label><input type="checkbox" checked={group.backfill_enabled} onChange={(event) => updateGroup(index, { backfill_enabled: event.target.checked })} /> Full history</label>
```

Stop rendering the numeric Backfill days field.

- [ ] **Step 4: Show history separately from live status**

On Indexer, retain live checkpoint and worker health. Add a History column/row containing status, percentage, cumulative headers and cumulative releases. Completed groups must visibly say `Complete`.

- [ ] **Step 5: Run frontend build/tests**

Run:

```bash
cd frontend
npm test -- --run
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat: show full-history indexing progress"
```

---

### Task 6: Prove upgrade safety, bounded memory, and end-to-end searchability

**Files:**
- Create: `tests/test_full_history_e2e.py`
- Modify: `tests/test_database_schema.py` or add a focused schema migration test.
- Modify benchmark fixtures/runner only if required to record the history metric.
- Modify: `README.md` with upgrade behavior and storage notes.

**Interfaces:**
- End-to-end path: provider overview -> historical window -> classifier -> compact DB rows -> `/api/releases/search` -> NZB/download article reconstruction.

- [ ] **Step 1: Write the RED E2E test**

Use a deterministic fake NNTP provider with a small retained range containing old and new audiobook releases plus junk. Run enough worker iterations to complete history, then assert old audiobook titles appear in `/api/releases/search`, junk does not, and the fake client recorded no BODY calls.

- [ ] **Step 2: Verify RED, then make only integration fixes required for GREEN**

Run: `pytest -q tests/test_full_history_e2e.py`

- [ ] **Step 3: Add migration upgrade test**

Start from schema revision `0007_runtime_orchestration`, insert a legacy `release_articles` row and provider credentials, upgrade to head, then assert the legacy article and encrypted credential columns/data remain present and readable.

- [ ] **Step 4: Add bounded-memory history benchmark**

Benchmark one 10,000-header historical window. The scanner must not accumulate previous windows in memory. Keep the existing benchmark gates and add a regression threshold only if the current benchmark harness supports stable memory assertions.

- [ ] **Step 5: Document the upgrade**

README must state:

```text
Full history is enabled by default for enabled audiobook groups. LoreX crawls overview headers only; it does not download audiobook bodies until Grab. Existing provider credentials and PostgreSQL data are migrated in place. Do not run docker compose down -v during upgrades.
```

- [ ] **Step 6: Run complete verification**

Run:

```bash
pytest -q
cd frontend && npm test -- --run && npm run build
```

Then run the repository's packaging and benchmark commands exactly as CI defines them.

Expected: all backend, frontend, packaging and benchmark gates PASS.

- [ ] **Step 7: Commit**

```bash
git add tests README.md benchmarks frontend
git commit -m "test: verify full-history index end to end"
```

---

## Self-review checklist

- Every spec requirement maps to Tasks 1-6.
- No task changes credential encryption or provider secrets.
- Compact persistence retains the physical filename needed by `PostProcessor` and the group/message-id/bytes needed for NZB/download behavior.
- Historical progress advances only after successful indexing, so crashes can cause duplicate work but not skipped ranges.
- Live checkpoint code remains monotonic and independent from descending historical state.
- One history window per scheduler iteration bounds memory and gives live scanning priority.
- Existing legacy release article rows remain readable after migration.
