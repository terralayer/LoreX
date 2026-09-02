def test_index_search_and_grab(client, mock_headers):
    indexed = client.post("/api/index/mock", json={"headers": mock_headers})
    assert indexed.status_code == 200
    assert indexed.json()["indexed"] == 1

    searched = client.get("/api/releases/search", params={"q": "Project Hail Mary"})
    assert searched.status_code == 200
    payload = searched.json()
    assert payload["count"] == 1
    release = payload["results"][0]
    assert release["author"] == "Andy Weir"
    assert release["title"] == "Project Hail Mary"
    assert release["narrator"] == "Ray Porter"
    assert release["format"] == "m4b"

    grabbed = client.post(f"/api/releases/{release['id']}/grab")
    assert grabbed.status_code == 200
    assert grabbed.json()["status"] == "queued"
    assert grabbed.json()["release_id"] == release["id"]
