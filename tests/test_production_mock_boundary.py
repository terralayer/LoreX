from fastapi.testclient import TestClient

from lorex.main import create_app


def _payload() -> dict:
    return {
        "headers": [
            {
                "message_id": "<synthetic-part-1@lorex.test>",
                "subject": "Synthetic Author - Synthetic Book.m4b [1/1]",
                "bytes": 1024,
                "group": "alt.binaries.audiobooks",
            }
        ]
    }


def test_mock_index_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("LOREX_ENABLE_MOCK_API", raising=False)
    app = create_app()

    with TestClient(app) as client:
        response = client.post("/api/index/mock", json=_payload())

    assert response.status_code == 404


def test_mock_index_can_be_enabled_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("LOREX_ENABLE_MOCK_API", "1")
    app = create_app()

    with TestClient(app) as client:
        response = client.post("/api/index/mock", json=_payload())

    assert response.status_code == 200
    assert set(response.json()) == {"indexed", "releases"}
