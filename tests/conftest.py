from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from lorex.db import create_engine_from_url
from lorex.main import app


@pytest.fixture
def client(monkeypatch):
    # Legacy vertical-slice API tests intentionally exercise LoreX's explicit
    # mock endpoint. Production keeps this disabled unless opted in.
    monkeypatch.setenv("LOREX_ENABLE_MOCK_API", "1")

    database_url = os.getenv("LOREX_DATABASE_URL")
    if database_url:
        engine = create_engine_from_url(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE activity_events, scanner_group_state, runtime_settings, "
                    "nntp_provider_groups, nntp_providers, provider_health, download_articles, "
                    "release_articles, indexer_checkpoints, releases, download_jobs, import_jobs, "
                    "library_books RESTART IDENTITY CASCADE"
                )
            )
        engine.dispose()

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_headers() -> list[dict]:
    fixture = Path(__file__).parent / "fixtures" / "mock_headers.json"
    return json.loads(fixture.read_text(encoding="utf-8"))
