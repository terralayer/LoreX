from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text


def _write_scanner_heartbeat(client, when: datetime) -> None:
    engine = client.app.state.container.engine
    assert engine is not None
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO runtime_settings (key, value, updated_at) "
                "VALUES (:key, :value, :updated_at) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
            ),
            {
                "key": "worker_heartbeat:nntp-scanner",
                "value": when.isoformat(),
                "updated_at": when,
            },
        )


def test_scan_now_rejects_request_when_scanner_worker_is_offline(client) -> None:
    response = client.post("/api/indexer/scan-now")

    assert response.status_code == 503
    assert "scanner worker is offline" in response.json()["detail"].lower()


def test_scan_now_accepts_request_when_scanner_worker_heartbeat_is_fresh(client) -> None:
    _write_scanner_heartbeat(client, datetime.now(UTC))

    response = client.post("/api/indexer/scan-now")

    assert response.status_code == 202
    status = client.get("/api/indexer/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload.get("worker_online") is True
    assert payload.get("worker_last_heartbeat_at") is not None


def test_scan_now_rejects_stale_scanner_worker_heartbeat(client) -> None:
    _write_scanner_heartbeat(client, datetime.now(UTC) - timedelta(seconds=30))

    response = client.post("/api/indexer/scan-now")

    assert response.status_code == 503
    assert "scanner worker is offline" in response.json()["detail"].lower()
