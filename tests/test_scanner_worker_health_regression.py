from __future__ import annotations

from base64 import urlsafe_b64encode
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from lorex.db import create_engine_from_url
from lorex.main import create_app
from lorex.nntp.protocol import GroupInfo
from lorex.workers.nntp_scanner import run_forever


def _credential_key() -> str:
    return urlsafe_b64encode(b"h" * 32).decode().rstrip("=")


def _reset_provider_db() -> None:
    database_url = os.getenv("LOREX_DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test")
    engine = create_engine_from_url(database_url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE nntp_provider_groups, nntp_providers CASCADE"))
    engine.dispose()


def test_scan_now_rejects_when_scanner_worker_is_offline(monkeypatch) -> None:
    if not os.getenv("LOREX_DATABASE_URL"):
        pytest.skip("PostgreSQL integration test")
    monkeypatch.setenv("LOREX_CREDENTIAL_KEY", _credential_key())
    monkeypatch.setenv("LOREX_EMBED_WORKERS", "0")

    with TestClient(create_app()) as client:
        status = client.get("/api/indexer/status")
        assert status.status_code == 200
        assert status.json()["worker_online"] is False
        assert status.json()["worker_last_heartbeat_at"] is None

        response = client.post("/api/indexer/scan-now")

    assert response.status_code == 503
    assert "scanner worker" in response.json()["detail"].lower()


def test_scanner_loop_publishes_worker_heartbeat() -> None:
    class RuntimeRepository:
        def __init__(self) -> None:
            self.heartbeats = 0

        def heartbeat_scanner_worker(self) -> None:
            self.heartbeats += 1

        def scanner_settings(self):
            return SimpleNamespace(enabled=False, scan_interval_seconds=300, scan_request_token=0)

    class StopAfterOneWait:
        def __init__(self) -> None:
            self.stopped = False

        def is_set(self) -> bool:
            return self.stopped

        def wait(self, _seconds: float) -> bool:
            self.stopped = True
            return True

    runtime = RuntimeRepository()
    run_forever(
        SimpleNamespace(list_enabled=lambda: []),
        object(),
        runtime,
        stop_event=StopAfterOneWait(),
    )

    assert runtime.heartbeats >= 1


def test_provider_connection_test_probes_scanner_overview_command(monkeypatch) -> None:
    _reset_provider_db()
    monkeypatch.setenv("LOREX_CREDENTIAL_KEY", _credential_key())
    monkeypatch.setenv("LOREX_EMBED_WORKERS", "0")
    calls: list[tuple] = []

    class FakeClient:
        def __init__(self, host: str, port: int):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def authenticate(self, username: str, password: str) -> None:
            calls.append(("auth", username, password))

        def group(self, name: str) -> GroupInfo:
            calls.append(("group", name))
            return GroupInfo(count=100, low=1, high=100, name=name)

        def xover(self, start: int, end: int):
            calls.append(("xover", start, end))
            return iter(())

    monkeypatch.setattr("lorex.api.nntp_settings.NntpClient", FakeClient)
    payload = {
        "name": "Newshosting",
        "host": "news.newshosting.com",
        "port": 563,
        "enabled": True,
        "priority": 20,
        "fill_server": True,
        "max_connections": 4,
        "username": "fixture-user",
        "password": "fixture-password",
        "groups": [{"group_name": "alt.binaries.audiobooks", "enabled": True}],
    }

    with TestClient(create_app()) as client:
        provider_id = client.post("/api/settings/nntp/providers", json=payload).json()["id"]
        response = client.post(f"/api/settings/nntp/providers/{provider_id}/test")

    assert response.status_code == 200
    assert calls == [
        ("connect", "news.newshosting.com", 563),
        ("auth", "fixture-user", "fixture-password"),
        ("group", "alt.binaries.audiobooks"),
        ("xover", 100, 100),
    ]


def test_api_lifespan_starts_embedded_workers_for_single_container(monkeypatch) -> None:
    if not os.getenv("LOREX_DATABASE_URL"):
        pytest.skip("PostgreSQL integration test")
    monkeypatch.setenv("LOREX_CREDENTIAL_KEY", _credential_key())
    monkeypatch.setenv("LOREX_EMBED_WORKERS", "1")
    started: list[str] = []

    def fake_scanner(*_args, **_kwargs) -> None:
        started.append("scanner")

    def fake_downloader(*_args, **_kwargs) -> None:
        started.append("downloader")

    monkeypatch.setattr("lorex.workers.nntp_scanner.run_forever", fake_scanner)
    monkeypatch.setattr("lorex.workers.download_worker.run_forever", fake_downloader)

    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200

    assert sorted(started) == ["downloader", "scanner"]


def test_compose_api_disables_embedded_workers_to_avoid_duplicates() -> None:
    compose = open("docker-compose.yml", encoding="utf-8").read()
    api_section = compose.split("  api:\n", 1)[1].split("\n  nntp-scanner:", 1)[0]
    assert 'LOREX_EMBED_WORKERS: "0"' in api_section
