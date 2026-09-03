def test_index_search_nzb_and_grab(client, mock_headers):
    indexed = client.post("/api/index/mock", json={"headers": mock_headers})
    assert indexed.status_code == 200
    assert indexed.json()["indexed"] == 1

    searched = client.get("/api/releases/search", params={"q": "Project Hail Mary"})
    assert searched.status_code == 200
    payload = searched.json()
    assert payload["total"] == 1
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    release = payload["results"][0]
    assert release["author"] == "Andy Weir"
    assert release["title"] == "Project Hail Mary"
    assert release["narrator"] == "Ray Porter"
    assert release["format"] == "m4b"
    assert "nzb" not in release
    assert "source_subject" not in release

    detail = client.get(f"/api/releases/{release['id']}")
    assert detail.status_code == 200
    assert detail.json()["nzb"] == ""
    assert detail.json()["source_subject"].startswith("Andy Weir - Project Hail Mary")

    nzb = client.get(f"/api/releases/{release['id']}/nzb")
    assert nzb.status_code == 200
    assert nzb.headers["content-type"].startswith("application/x-nzb")
    assert nzb.text.startswith("<?xml")
    for header in mock_headers:
        if "Project Hail Mary" in header["subject"]:
            assert header["message_id"].strip("<>") in nzb.text

    grabbed = client.post(f"/api/releases/{release['id']}/grab")
    assert grabbed.status_code == 200
    assert grabbed.json()["status"] == "queued"
    assert grabbed.json()["release_id"] == release["id"]


def test_release_search_is_bounded_and_paginated(client, mock_headers):
    client.post("/api/index/mock", json={"headers": mock_headers})

    response = client.get(
        "/api/releases/search",
        params={"limit": 1, "offset": 0, "sort": "author", "order": "desc", "format": "m4b"},
    )

    assert response.status_code == 200
    assert response.json()["limit"] == 1
    assert len(response.json()["results"]) <= 1


def test_release_search_rejects_invalid_parameters(client):
    for params in (
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"sort": "nzb"},
        {"order": "sideways"},
    ):
        response = client.get("/api/releases/search", params=params)
        assert response.status_code == 422, params


def test_release_detail_returns_404(client):
    response = client.get("/api/releases/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Release not found"}


def test_dashboard_summary_returns_counts_without_release_rows(client, mock_headers):
    client.post("/api/index/mock", json={"headers": mock_headers})

    response = client.get("/api/library/dashboard")

    assert response.status_code == 200
    assert response.json() == {
        "total_releases": 1,
        "download_statuses": {"untracked": 1},
        "import_statuses": {"untracked": 1},
    }
