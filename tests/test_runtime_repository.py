from __future__ import annotations

import os

import pytest
from sqlalchemy import delete

from lorex.db import create_engine_from_url, session_factory
from lorex.db_models import ActivityEventRow, NntpProviderRow, RuntimeSettingRow, ScannerGroupStateRow
from lorex.runtime_repository import PostgresRuntimeRepository


PROVIDER_ID = "runtime-test-provider"


def _repository():
    database_url = os.getenv("LOREX_DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test")
    engine = create_engine_from_url(database_url)
    sessions = session_factory(engine)
    with sessions.begin() as session:
        session.execute(delete(ActivityEventRow))
        session.execute(delete(ScannerGroupStateRow))
        session.execute(delete(RuntimeSettingRow))
        session.execute(delete(NntpProviderRow).where(NntpProviderRow.id == PROVIDER_ID))
        session.add(
            NntpProviderRow(
                id=PROVIDER_ID,
                name="Runtime Test Provider",
                host="news.example.invalid",
                port=563,
                enabled=True,
                priority=100,
                fill_server=False,
                max_connections=4,
            )
        )
    return engine, PostgresRuntimeRepository(sessions)


def test_runtime_settings_have_safe_defaults_and_persist_updates() -> None:
    engine, repo = _repository()
    try:
        settings = repo.scanner_settings()
        assert settings.enabled is False
        assert settings.scan_interval_seconds == 300
        assert settings.scan_request_token == 0

        updated = repo.update_scanner_settings(enabled=True, scan_interval_seconds=42)
        assert updated.enabled is True
        assert updated.scan_interval_seconds == 42
        assert repo.scanner_settings() == updated

        assert repo.request_scan_now() == 1
        assert repo.request_scan_now() == 2
        assert repo.scanner_settings().scan_request_token == 2
    finally:
        engine.dispose()


def test_scanner_state_and_activity_are_durable() -> None:
    engine, repo = _repository()
    try:
        repo.mark_scan_started(PROVIDER_ID, "alt.binaries.audiobooks")
        repo.mark_scan_completed(
            PROVIDER_ID,
            "alt.binaries.audiobooks",
            scanned_count=120,
            indexed_count=7,
        )
        state = repo.scanner_states()[0]
        assert state.status == "idle"
        assert state.last_scanned_count == 120
        assert state.last_indexed_count == 7
        assert state.last_error is None
        assert state.last_started_at is not None
        assert state.last_completed_at is not None

        repo.append_activity("scanner", "Indexed audiobook headers", entity_id=PROVIDER_ID)
        events = repo.recent_activity(limit=10)
        assert len(events) == 1
        assert events[0].kind == "scanner"
        assert events[0].message == "Indexed audiobook headers"
        assert events[0].entity_id == PROVIDER_ID
    finally:
        engine.dispose()
