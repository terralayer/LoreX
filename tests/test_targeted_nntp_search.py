from __future__ import annotations

from dataclasses import dataclass, field

from lorex.nntp.models import NntpProvider, NntpProviderGroup
from lorex.nntp.protocol import GroupInfo, OverviewRecord
from lorex.repository import ReleaseRepository
from lorex.services.on_demand_search import BookSearchRequest


def _targeted_scan():
    from lorex.services.targeted_nntp_search import scan_requested_book_group

    return scan_requested_book_group


@dataclass
class ScriptedClient:
    rows: list[OverviewRecord]
    low: int = 1
    high: int = 1000
    requested_ranges: list[tuple[int, int]] = field(default_factory=list)
    authenticated: tuple[str, str] | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def authenticate(self, username: str, password: str) -> None:
        self.authenticated = (username, password)

    def group(self, name: str) -> GroupInfo:
        return GroupInfo(count=self.high - self.low + 1, low=self.low, high=self.high, name=name)

    def xover(self, start: int, end: int):
        self.requested_ranges.append((start, end))
        return (row for row in self.rows if start <= row.article_number <= end)


def _provider() -> NntpProvider:
    return NntpProvider(
        id="a" * 32,
        name="Primary",
        host="news.example.test",
        username="fixture-user",
        password="fixture-password",
    )


def _group(batch_size: int = 100) -> NntpProviderGroup:
    return NntpProviderGroup("alt.binaries.audiobooks", scan_batch_size=batch_size)


def _row(number: int, filename: str) -> OverviewRecord:
    return OverviewRecord(
        article_number=number,
        subject=f'"{filename}" yEnc (1/1)',
        message_id=f"<{number}@test>",
        bytes=123_456_789,
    )


def test_requested_book_scan_discards_unrelated_headers_and_does_not_advance_global_checkpoint() -> None:
    provider = _provider()
    group = _group()
    repository = ReleaseRepository()
    client = ScriptedClient(
        [
            _row(980, "Andy Weir - Project Hail Mary.m4b"),
            _row(990, "Someone Else - Completely Different Book.m4b"),
        ]
    )

    stats = _targeted_scan()(
        provider,
        group,
        repository,
        BookSearchRequest(title="Project Hail Mary", author="Andy Weir"),
        client_factory=lambda _: client,
        max_windows=1,
    )

    assert client.authenticated == ("fixture-user", "fixture-password")
    assert client.requested_ranges == [(901, 1000)]
    assert stats.headers_examined == 2
    assert stats.headers_matched == 1
    assert stats.releases_indexed == 1
    assert len(repository.search("Project Hail Mary")) == 1
    assert repository.search("Completely Different Book") == []
    assert repository.get_checkpoint(provider.id, group.group_name) is None


def test_requested_book_scan_walks_backward_only_until_it_finds_matching_headers() -> None:
    provider = _provider()
    group = _group()
    repository = ReleaseRepository()
    client = ScriptedClient(
        [
            _row(850, "Andy Weir - Project Hail Mary.m4b"),
            _row(950, "Someone Else - Completely Different Book.m4b"),
        ]
    )

    stats = _targeted_scan()(
        provider,
        group,
        repository,
        BookSearchRequest(title="Project Hail Mary", author="Andy Weir"),
        client_factory=lambda _: client,
        max_windows=5,
    )

    assert client.requested_ranges == [(901, 1000), (801, 900)]
    assert stats.windows_scanned == 2
    assert stats.headers_matched == 1
    assert len(repository.search("Project Hail Mary")) == 1
    assert repository.get_checkpoint(provider.id, group.group_name) is None


def test_requested_book_scan_requires_title_evidence_even_when_author_matches() -> None:
    provider = _provider()
    group = _group()
    repository = ReleaseRepository()
    client = ScriptedClient([_row(980, "Andy Weir - The Martian.m4b")])

    stats = _targeted_scan()(
        provider,
        group,
        repository,
        BookSearchRequest(title="Project Hail Mary", author="Andy Weir"),
        client_factory=lambda _: client,
        max_windows=1,
    )

    assert stats.headers_matched == 0
    assert repository.search("") == []
