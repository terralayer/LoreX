def test_grab_processes_into_managed_library(client, mock_headers):
    client.post("/api/index/mock", json={"headers": mock_headers})
    release = client.get("/api/releases/search", params={"q": "Project Hail Mary"}).json()["results"][0]
    client.post(f"/api/releases/{release['id']}/grab")

    processed = client.post("/api/downloads/process-next")
    assert processed.status_code == 200
    assert processed.json()["status"] == "completed"

    library = client.get("/api/library/books")
    assert library.status_code == 200
    payload = library.json()
    assert payload["count"] == 1
    book = payload["books"][0]
    assert book["title"] == "Project Hail Mary"
    assert book["author"] == "Andy Weir"
    assert book["narrator"] == "Ray Porter"
    assert book["format"] == "m4b"
    assert book["path"] == "/library/Andy Weir/Project Hail Mary/Project Hail Mary.m4b"
