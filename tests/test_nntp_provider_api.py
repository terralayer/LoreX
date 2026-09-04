from __future__ import annotations

from base64 import urlsafe_b64encode
import os

from fastapi.testclient import TestClient
from sqlalchemy import text

from lorex.db import create_engine_from_url
from lorex.main import create_app

TEST_USERNAME = "fixture-user"
TEST_PASSWORD = "fixture-value"


def _key() -> str:
    return urlsafe_b64encode(b"a" * 32).decode().rstrip("=")


def _reset_db() -> None:
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE nntp_provider_groups, nntp_providers CASCADE"))
    engine.dispose()


def _payload() -> dict:
    return {
        "name": "Primary",
        "host": "news.example.test",
        "port": 563,
        "enabled": True,
        "priority": 10,
        "fill_server": False,
        "max_connections": 8,
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
        "groups": [
            {
                "group_name": "alt.binaries.audiobooks",
                "enabled": True,
                "scan_batch_size": 5000,
                "backfill_days": 365,
            }
        ],
    }


def _assert_masked(payload: dict) -> None:
    serialized = str(payload)
    assert TEST_USERNAME not in serialized
    assert TEST_PASSWORD not in serialized
    assert "username_encrypted" not in serialized
    assert "password_encrypted" not in serialized
    assert payload["username_configured"] is True
    assert payload["password_configured"] is True
    assert "username" not in payload
    assert "password" not in payload


def test_create_list_and_patch_provider_never_return_plaintext_credentials(monkeypatch):
    _reset_db()
    monkeypatch.setenv("LOREX_CREDENTIAL_KEY", _key())
    with TestClient(create_app()) as client:
        created_response = client.post("/api/settings/nntp/providers", json=_payload())
        assert created_response.status_code == 201
        created = created_response.json()
        _assert_masked(created)
        provider_id = created["id"]

        listed_response = client.get("/api/settings/nntp/providers")
        assert listed_response.status_code == 200
        listed = listed_response.json()
        assert listed["count"] == 1
        _assert_masked(listed["providers"][0])

        patched_response = client.patch(
            f"/api/settings/nntp/providers/{provider_id}",
            json={"host": "news2.example.test"},
        )
        assert patched_response.status_code == 200
        patched = patched_response.json()
        assert patched["host"] == "news2.example.test"
        _assert_masked(patched)


def test_explicit_credential_clear_is_masked(monkeypatch):
    _reset_db()
    monkeypatch.setenv("LOREX_CREDENTIAL_KEY", _key())
    with TestClient(create_app()) as client:
        provider_id = client.post("/api/settings/nntp/providers", json=_payload()).json()["id"]
        response = client.post(f"/api/settings/nntp/providers/{provider_id}/credentials/password/clear")
        assert response.status_code == 200
        body = response.json()
        assert body["username_configured"] is True
        assert body["password_configured"] is False
        assert TEST_PASSWORD not in str(body)


def test_delete_provider(monkeypatch):
    _reset_db()
    monkeypatch.setenv("LOREX_CREDENTIAL_KEY", _key())
    with TestClient(create_app()) as client:
        provider_id = client.post("/api/settings/nntp/providers", json=_payload()).json()["id"]
        response = client.delete(f"/api/settings/nntp/providers/{provider_id}")
        assert response.status_code == 204
        assert client.get("/api/settings/nntp/providers").json() == {"count": 0, "providers": []}


def test_masked_list_works_without_master_key(monkeypatch):
    _reset_db()
    monkeypatch.setenv("LOREX_CREDENTIAL_KEY", _key())
    with TestClient(create_app()) as client:
        assert client.post("/api/settings/nntp/providers", json=_payload()).status_code == 201

    monkeypatch.delenv("LOREX_CREDENTIAL_KEY", raising=False)
    with TestClient(create_app()) as client:
        response = client.get("/api/settings/nntp/providers")
        assert response.status_code == 200
        _assert_masked(response.json()["providers"][0])


def test_secret_writes_fail_503_when_master_key_is_missing(monkeypatch):
    _reset_db()
    monkeypatch.delenv("LOREX_CREDENTIAL_KEY", raising=False)
    with TestClient(create_app()) as client:
        response = client.post("/api/settings/nntp/providers", json=_payload())
        assert response.status_code == 503
        assert "credential" in response.json()["detail"].lower()
        assert TEST_PASSWORD not in response.text
