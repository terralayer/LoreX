from __future__ import annotations


def test_indexer_settings_and_scan_now_are_durable(client) -> None:
    created = client.post(
        "/api/settings/nntp/providers",
        json={
            "name": "Indexer API Provider",
            "host": "news.example.invalid",
            "port": 563,
            "enabled": True,
            "priority": 100,
            "fill_server": False,
            "max_connections": 4,
            "groups": [
                {
                    "group_name": "alt.binaries.audiobooks",
                    "enabled": True,
                    "scan_batch_size": 5000,
                    "backfill_days": 0,
                }
            ],
        },
    )
    assert created.status_code == 201

    patched = client.patch(
        "/api/indexer/settings",
        json={"enabled": False, "scan_interval_seconds": 60},
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False
    assert patched.json()["scan_interval_seconds"] == 60

    requested = client.post("/api/indexer/scan-now")
    assert requested.status_code == 202
    assert requested.json()["scan_request_token"] >= 1

    status = client.get("/api/indexer/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["enabled"] is False
    assert payload["scan_interval_seconds"] == 60
    assert payload["scan_request_token"] == requested.json()["scan_request_token"]
    assert len(payload["groups"]) == 1
    group = payload["groups"][0]
    assert group["provider_name"] == "Indexer API Provider"
    assert group["group_name"] == "alt.binaries.audiobooks"
    assert group["status"] == "idle"
    assert group["checkpoint_article"] is None
    assert "username" not in group
    assert "password" not in group
