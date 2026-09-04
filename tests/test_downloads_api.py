from __future__ import annotations


def _release(client, mock_headers):
    indexed = client.post("/api/index/mock", json={"headers": mock_headers})
    assert indexed.status_code == 200
    results = client.get("/api/releases/search", params={"q": "Project Hail Mary"}).json()["results"]
    return results[0]


def test_grab_is_idempotent_and_download_queue_is_visible(client, mock_headers) -> None:
    release = _release(client, mock_headers)

    first = client.post(f"/api/releases/{release['id']}/grab")
    second = client.post(f"/api/releases/{release['id']}/grab")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    queue = client.get("/api/downloads")
    assert queue.status_code == 200
    jobs = queue.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["id"] == first.json()["id"]
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["title"] == "Project Hail Mary"


def test_cancel_and_retry_are_explicit(client, mock_headers) -> None:
    release = _release(client, mock_headers)
    job = client.post(f"/api/releases/{release['id']}/grab").json()

    canceled = client.post(f"/api/downloads/{job['id']}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"

    retried = client.post(f"/api/downloads/{job['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
