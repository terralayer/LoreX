from __future__ import annotations


def test_activity_api_returns_recent_runtime_events(client) -> None:
    runtime = client.app.state.container.runtime
    assert runtime is not None
    runtime.append_activity("scanner", "Indexed live headers", entity_id="provider-1", detail="12 releases")
    runtime.append_activity("download", "Completed live import", entity_id="job-1")

    response = client.get("/api/activity", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [event["kind"] for event in payload["events"]] == ["download", "scanner"]
    assert payload["events"][0]["message"] == "Completed live import"
    assert payload["events"][1]["detail"] == "12 releases"
    assert payload["events"][0]["created_at"]


def test_activity_api_bounds_limit(client) -> None:
    assert client.get("/api/activity", params={"limit": 0}).status_code == 422
    assert client.get("/api/activity", params={"limit": 201}).status_code == 422
