from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lorex.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_headers() -> list[dict]:
    fixture = Path(__file__).parent / "fixtures" / "mock_headers.json"
    return json.loads(fixture.read_text(encoding="utf-8"))
