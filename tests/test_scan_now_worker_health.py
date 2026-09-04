from __future__ import annotations


def test_scan_now_rejects_request_when_scanner_worker_is_offline(client) -> None:
    response = client.post("/api/indexer/scan-now")

    assert response.status_code == 503
    assert "scanner worker is offline" in response.json()["detail"].lower()


def test_scan_now_accepts_request_when_scanner_worker_heartbeat_is_fresh(client) -> None:
    runtime = client.app.state.container.runtime
    assert runtime is not None
    runtime.touch_worker_heartbeat("nntp-scanner")

    response = client.post("/api/indexer/scan-now")

    assert response.status_code == 202
    status = client.get("/api/indexer/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["worker_online"] is True
    assert payload["worker_last_heartbeat_at"] is not None
