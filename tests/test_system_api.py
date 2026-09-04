from __future__ import annotations


def test_system_summary_is_honest_on_empty_database(client) -> None:
    response = client.get("/api/system/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["providers_configured"] == 0
    assert payload["providers_enabled"] == 0
    assert payload["groups_enabled"] == 0
    assert payload["library_books"] == 0
    assert payload["total_releases"] == 0
    assert payload["downloads"] == {}
    assert payload["provider_health"] == []
    assert payload["recent_releases"] == []
    assert payload["recent_downloads"] == []
    assert payload["recent_activity"] == []
    assert "No Usenet provider is configured" in payload["configuration_issues"]


def test_system_summary_reports_only_measured_provider_health(client, mock_headers) -> None:
    created = client.post(
        "/api/settings/nntp/providers",
        json={
            "name": "Synthetic Provider",
            "host": "news.example.test",
            "port": 563,
            "enabled": True,
            "priority": 10,
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

    client.post("/api/index/mock", json={"headers": mock_headers})
    jobs = client.app.state.container.jobs
    jobs.record_provider_attempt(
        "Synthetic Provider",
        success=True,
        fallback=False,
        byte_count=1_048_576,
        elapsed_ms=1000.0,
    )

    response = client.get("/api/system/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["providers_configured"] == 1
    assert payload["providers_enabled"] == 1
    assert payload["groups_enabled"] == 1
    assert payload["total_releases"] == 1
    assert len(payload["recent_releases"]) == 1
    health = payload["provider_health"][0]
    assert health["provider"] == "Synthetic Provider"
    assert health["attempts"] == 1
    assert health["successes"] == 1
    assert health["success_rate"] == 1.0
    assert health["throughput_mib_s"] == 1.0


def test_system_summary_does_not_invent_speed_before_measurement(client) -> None:
    created = client.post(
        "/api/settings/nntp/providers",
        json={
            "name": "Unmeasured Provider",
            "host": "news.example.test",
            "groups": [{"group_name": "alt.binaries.audiobooks"}],
        },
    )
    assert created.status_code == 201

    payload = client.get("/api/system/summary").json()
    health = payload["provider_health"][0]
    assert health["attempts"] == 0
    assert health["success_rate"] is None
    assert health["throughput_mib_s"] is None
