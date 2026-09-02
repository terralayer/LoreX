def test_index_search_nzb_and_grab(client, mock_headers):
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
    assert release["nzb"] == ""

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
