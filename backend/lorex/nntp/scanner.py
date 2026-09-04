from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from lorex.domain import ArticleHeader, IndexCheckpoint
from lorex.nntp.client import NntpClient
from lorex.nntp.models import NntpProvider, NntpProviderGroup
from lorex.nntp.protocol import GroupInfo, OverviewRecord
from lorex.services.indexing import IndexBatch, index_batches


class _ScannerClient(Protocol):
    def __enter__(self): ...
    def __exit__(self, exc_type, exc, tb): ...
    def authenticate(self, username: str, password: str) -> None: ...
    def group(self, name: str) -> GroupInfo: ...
    def xover(self, start: int, end: int): ...


@dataclass(frozen=True, slots=True)
class ScanStats:
    range_start: int | None
    range_end: int | None
    headers_received: int
    releases_indexed: int = 0
    releases_rejected: int = 0
    duplicate_releases: int = 0


def _default_client_factory(provider: NntpProvider) -> NntpClient:
    return NntpClient(provider.host, provider.port)


def _scan_range(
    *,
    checkpoint: IndexCheckpoint | None,
    group_info: GroupInfo,
    batch_size: int,
    mode: str,
) -> tuple[int, int] | None:
    if checkpoint is not None:
        if checkpoint.article_number >= group_info.high:
            return None
        start = max(group_info.low, checkpoint.article_number + 1)
    elif mode == "live":
        start = max(group_info.low, group_info.high - batch_size + 1)
    elif mode == "backfill":
        start = group_info.low
    else:
        raise ValueError("mode must be 'live' or 'backfill'")

    if start > group_info.high:
        return None
    end = min(group_info.high, start + batch_size - 1)
    return start, end


def scan_group_once(
    provider: NntpProvider,
    group: NntpProviderGroup,
    repository,
    *,
    client_factory: Callable[[NntpProvider], _ScannerClient] = _default_client_factory,
    mode: str = "live",
) -> ScanStats:
    """Scan at most one configured overview window and durably advance its checkpoint.

    The complete overview response is materialized before any database write. This
    deliberately prevents a mid-response disconnect from advancing the checkpoint.
    The checkpoint is committed through the release repository only after a complete
    range has been received, so sparse ranges still advance to the requested end.
    """

    checkpoint = repository.get_checkpoint(provider.id, group.group_name)

    with client_factory(provider) as client:
        if provider.username is not None or provider.password is not None:
            if provider.username is None or provider.password is None:
                raise ValueError("NNTP username and password must be configured together")
            client.authenticate(provider.username, provider.password)

        group_info = client.group(group.group_name)
        requested = _scan_range(
            checkpoint=checkpoint,
            group_info=group_info,
            batch_size=group.scan_batch_size,
            mode=mode,
        )
        if requested is None:
            return ScanStats(None, None, 0)

        start, end = requested
        rows: list[OverviewRecord] = list(client.xover(start, end))

    headers = [
        ArticleHeader(
            message_id=row.message_id,
            subject=row.subject,
            bytes=row.bytes,
            group=group.group_name,
        )
        for row in rows
    ]
    durable_checkpoint = IndexCheckpoint(provider.id, group.group_name, end)
    indexing = index_batches(
        [IndexBatch(headers=headers, checkpoint=durable_checkpoint)],
        repository,
        batch_size=max(1, min(group.scan_batch_size, 512)),
    )
    return ScanStats(
        range_start=start,
        range_end=end,
        headers_received=indexing.headers_received,
        releases_indexed=indexing.releases_indexed,
        releases_rejected=indexing.releases_rejected,
        duplicate_releases=indexing.duplicate_releases,
    )
