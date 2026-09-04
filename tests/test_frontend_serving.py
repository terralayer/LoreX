from pathlib import Path

from fastapi.testclient import TestClient

from lorex.main import create_app


def test_frontend_root_and_spa_routes_are_served(tmp_path: Path, monkeypatch) -> None:
    dist = tmp_path / "frontend-dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>LoreX frontend</body></html>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    client = TestClient(create_app())

    root = client.get("/")
    assert root.status_code == 200
    assert root.headers["content-type"].startswith("text/html")
    assert "LoreX frontend" in root.text

    spa = client.get("/library")
    assert spa.status_code == 200
    assert spa.headers["content-type"].startswith("text/html")
    assert "LoreX frontend" in spa.text


def test_unknown_api_route_remains_json_404(tmp_path: Path, monkeypatch) -> None:
    dist = tmp_path / "frontend-dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>LoreX frontend</body></html>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    client = TestClient(create_app())
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
