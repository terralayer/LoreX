from __future__ import annotations

import os

import pytest
from sqlalchemy import inspect

from lorex.db import create_engine_from_url


def test_runtime_orchestration_schema_exists() -> None:
    database_url = os.getenv("LOREX_DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test")

    engine = create_engine_from_url(database_url)
    try:
        inspector = inspect(engine)
        assert "scanner_group_state" in inspector.get_table_names()
        assert "runtime_settings" in inspector.get_table_names()
        assert "activity_events" in inspector.get_table_names()

        download_columns = {column["name"] for column in inspector.get_columns("download_jobs")}
        assert {"error", "cancel_requested", "completed_at"} <= download_columns
    finally:
        engine.dispose()
