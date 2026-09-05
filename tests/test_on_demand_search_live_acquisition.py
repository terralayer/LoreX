from __future__ import annotations

from dataclasses import dataclass

from lorex.nntp.models import NntpProvider, NntpProviderGroup
from lorex.nntp.protocol import GroupInfo, OverviewRecord


class ProviderRepository:
    def __init__(self, provider: NntpProvider) -> None:
        self.provider = provider

    def list_enabled(self):
        return (self.provider,)


@dataclass
class SearchClient:
    rows: list[OverviewRecord]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def authenticate(self, username: str, password: str) -> None:
        return None

    def group(self, name: str) -> GroupInfo:
        return GroupInfo(count=100, low=901, high=1000, name=name)

    def xover(self, start: int, end: int):
        return (row for row in self.rows if start <= row.article_number <= end)


def _row(number: int, filename: str) -> OverviewRecord:
    return OverviewRecord(
        article_number=number,
        subject=f'"{filename}" yEnc (1/1)',
        message_id=f"<{number}@search.test>",
        bytes=500_000_000,
    )


def test_search_acquires_requested_book_from_nntp_without_indexing_unrelated_book(client) -> None:
    group = NntpProviderGroup("alt.binaries.audiobooks", scan_batch_size=100)
    provider = NntpProvider(
        id="b" * 32,
        name="Search Provider",
        host="news.example.test",
        groups=(group,),
    )
    search_client = SearchClient(
        rows=[
            _row(970, "Andy Weir - Project Hail Mary.m4b"),
            _row(980, "Other Author - Other Book.m4b"),
        ]
    )
    container = client.app.state.container
    container.nntp_providers = ProviderRepository(provider)
    container.nntp_client_factory = lambda _: search_client
    container.credential_key_available = True

    response = client.post(
        "/api/search/on-demand",
        json={"title": "Project Hail Mary", "author": "Andy Weir", "max_scan_windows": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert payload["results"][0]["release"]["title"] == "Project Hail Mary"
    assert payload["acquisition"]["headers_matched"] == 1
    assert container.releases.search("Other Book") == []
    assert container.releases.get_checkpoint(provider.id, group.group_name) is None
