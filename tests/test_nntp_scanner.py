from __future__ import annotations

from dataclasses import dataclass

import pytest

from lorex.domain import IndexCheckpoint
from lorex.nntp.models import NntpProvider, NntpProviderGroup
from lorex.nntp.protocol import GroupInfo, OverviewRecord
from lorex.nntp.scanner import scan_group_once


class MemoryReleaseRepository:
    def __init__(self, checkpoint: IndexCheckpoint | None = None, *, fail_commit: bool = False) -> None:
        self.checkpoint = checkpoint
        self.fail_commit = fail_commit
        self.commits: list[tuple[list[tuple[object, tuple[object, ...]]], IndexCheckpoint | None]] = []

    def get_checkpoint(self, source: str, group: str) -> IndexCheckpoint | None:
        if self.checkpoint and self.checkpoint.source == source and self.checkpoint.group == group:
            return self.checkpoint
        return None

    def commit_index_batch(self, records, checkpoint=None) -> int:
        if self.fail_commit:
            raise RuntimeError("fixture database failure")
        materialized = list(records)
        self.commits.append((materialized, checkpoint))
        if checkpoint is not None:
            if self.checkpoint and checkpoint.article_number < self.checkpoint.article_number:
                raise ValueError("checkpoint cannot move backwards")
            self.checkpoint = checkpoint
        return len(materialized)

    def search(self, query: str):
        return []


@dataclass
class ScriptedClient:
    rows: list[OverviewRecord]
    low: int = 1
    high: int = 1000
    fail_during_overview: bool = False
    authenticated: tuple[str, str] | None = None
    selected_group: str | None = None
    requested_range: tuple[int, int] | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def authenticate(self, username: str, password: str) -> None:
        self.authenticated = (username, password)

    def group(self, name: str) -> GroupInfo:
        self.selected_group = name
        return GroupInfo(count=self.high - self.low + 1, low=self.low, high=self.high, name=name)

    def xover(self, start: int, end: int):
        self.requested_range = (start, end)
        for row in self.rows:
            if start <= row.article_number <= end:
                yield row
        if self.fail_during_overview:
            raise ConnectionError("fixture disconnect")


def _provider(*, provider_id: str = "a" * 32, name: str = "Primary") -> NntpProvider:
    return NntpProvider(
        id=provider_id,
        name=name,
        host="news.example.test",
        username="fixture-user",
        password="fixture-value",
    )


def _group(batch_size: int = 100) -> NntpProviderGroup:
    return NntpProviderGroup("alt.binaries.audiobooks", scan_batch_size=batch_size)


def _row(number: int, subject: str = "Author - Book.m4b (1/1)") -> OverviewRecord:
    return OverviewRecord(number, subject, f"<{number}@test>", 1234)


def test_scanner_resumes_after_persisted_checkpoint_and_commits_range_end():
    provider = _provider()
    group = _group(100)
    repository = MemoryReleaseRepository(IndexCheckpoint(provider.id, group.group_name, 100))
    client = ScriptedClient([_row(101), _row(150), _row(200)], low=1, high=500)

    stats = scan_group_once(provider, group, repository, client_factory=lambda _: client)

    assert client.authenticated == ("fixture-user", "fixture-value")
    assert client.selected_group == group.group_name
    assert client.requested_range == (101, 200)
    assert repository.checkpoint == IndexCheckpoint(provider.id, group.group_name, 200)
    assert stats.range_start == 101
    assert stats.range_end == 200
    assert stats.headers_received == 3


def test_sparse_successful_range_advances_to_requested_end_not_last_returned_row():
    provider = _provider()
    group = _group(100)
    repository = MemoryReleaseRepository(IndexCheckpoint(provider.id, group.group_name, 100))
    client = ScriptedClient([_row(105)], low=1, high=500)

    stats = scan_group_once(provider, group, repository, client_factory=lambda _: client)

    assert repository.checkpoint == IndexCheckpoint(provider.id, group.group_name, 200)
    assert stats.headers_received == 1


def test_disconnect_before_complete_overview_does_not_advance_checkpoint():
    provider = _provider()
    group = _group(100)
    original = IndexCheckpoint(provider.id, group.group_name, 100)
    repository = MemoryReleaseRepository(original)
    client = ScriptedClient([_row(101)], low=1, high=500, fail_during_overview=True)

    with pytest.raises(ConnectionError):
        scan_group_once(provider, group, repository, client_factory=lambda _: client)

    assert repository.checkpoint == original
    assert repository.commits == []


def test_database_failure_does_not_advance_checkpoint():
    provider = _provider()
    group = _group(100)
    original = IndexCheckpoint(provider.id, group.group_name, 100)
    repository = MemoryReleaseRepository(original, fail_commit=True)
    client = ScriptedClient([_row(101)], low=1, high=500)

    with pytest.raises(RuntimeError, match="fixture database failure"):
        scan_group_once(provider, group, repository, client_factory=lambda _: client)

    assert repository.checkpoint == original


def test_provider_rename_keeps_checkpoint_identity_by_provider_id():
    provider_id = "b" * 32
    group = _group(100)
    repository = MemoryReleaseRepository(IndexCheckpoint(provider_id, group.group_name, 300))
    renamed = _provider(provider_id=provider_id, name="Renamed Provider")
    client = ScriptedClient([_row(301)], low=1, high=500)

    scan_group_once(renamed, group, repository, client_factory=lambda _: client)

    assert client.requested_range == (301, 400)
    assert repository.checkpoint == IndexCheckpoint(provider_id, group.group_name, 400)


def test_first_live_scan_starts_at_bounded_tail_of_group():
    provider = _provider()
    group = _group(100)
    repository = MemoryReleaseRepository()
    client = ScriptedClient([_row(901)], low=1, high=1000)

    scan_group_once(provider, group, repository, client_factory=lambda _: client, mode="live")

    assert client.requested_range == (901, 1000)
    assert repository.checkpoint == IndexCheckpoint(provider.id, group.group_name, 1000)


def test_first_backfill_scan_starts_at_group_low_water_mark():
    provider = _provider()
    group = _group(100)
    repository = MemoryReleaseRepository()
    client = ScriptedClient([_row(10)], low=10, high=1000)

    scan_group_once(provider, group, repository, client_factory=lambda _: client, mode="backfill")

    assert client.requested_range == (10, 109)
    assert repository.checkpoint == IndexCheckpoint(provider.id, group.group_name, 109)


def test_checkpoint_at_or_above_server_high_is_noop_and_never_moves_backwards():
    provider = _provider()
    group = _group(100)
    original = IndexCheckpoint(provider.id, group.group_name, 1000)
    repository = MemoryReleaseRepository(original)
    client = ScriptedClient([], low=1, high=900)

    stats = scan_group_once(provider, group, repository, client_factory=lambda _: client)

    assert client.requested_range is None
    assert repository.checkpoint == original
    assert stats.headers_received == 0
    assert stats.range_start is None
    assert stats.range_end is None
