from __future__ import annotations


def test_on_demand_search_api_scores_and_returns_only_plausible_matches(client) -> None:
    indexed = client.post(
        "/api/index/mock",
        json={
            "headers": [
                {
                    "message_id": "<phm-1@example>",
                    "subject": "Andy.Weir.Project.Hail.Mary.M4B yEnc (1/1)",
                    "bytes": 812_000_000,
                    "group": "alt.binaries.audiobooks",
                },
                {
                    "message_id": "<video-1@example>",
                    "subject": "Project.Hail.Mary.2160p.WEB-DL.mkv yEnc (1/1)",
                    "bytes": 4_000_000_000,
                    "group": "alt.binaries.audiobooks",
                },
            ]
        },
    )
    assert indexed.status_code == 200

    response = client.post(
        "/api/search/on-demand",
        json={"title": "Project Hail Mary", "author": "Andy Weir"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["queries"]
    assert payload["results"]
    assert payload["results"][0]["score"] >= 80
    assert payload["results"][0]["bucket"] == "likely"
    assert payload["results"][0]["release"]["title"] == "Project Hail Mary"
    assert all(item["bucket"] != "hidden" for item in payload["results"])
