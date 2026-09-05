from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Protocol

from lorex.domain import ArticleHeader
from lorex.nntp.client import NntpClient
from lorex.nntp.models import NntpProvider, NntpProviderGroup
from lorex.nntp.protocol import GroupInfo
from lorex.services.indexing import IndexBatch, index_batches
from lorex.services.on_demand_search import BookSearchRequest


class _TargetedClient(Protocol):
    def __enter__(self): ...
    def __exit__(self, exc_type, exc, tb): ...
    def authenticate(self, username: str, password: str) -> None: ...
    def group(self, name: str) -> GroupInfo: ...
    def xover(self, start: int, end: int): ...


@dataclass(frozen=True, slots=True)
class TargetedScanStats:
    windows_scanned: int = 0
    headers_examined: int = 0
    headers_matched: int = 0
    releases_indexed: int = 0
    releases_rejected: int = 0
    duplicate_releases: int = 0


@dataclass(frozen=True, slots=True)
class TargetedAcquisitionStats:
    groups_searched: int = 0
    windows_scanned: int = 0
    headers_examined: int = 0
    headers_matched: int = 0
    releases_indexed: int = 0
    releases_rejected: int = 0
    duplicate_releases: int = 0


def _default_client_factory(provider: NntpProvider) -> NntpClient:
    return NntpClient(provider.host, provider.port)


def _tokens(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def subject_matches_request(subject: str, request: BookSearchRequest) -> bool:
    """Return True only when a subject contains strong title evidence.

    NNTP overview has no portable server-side full-text search, so LoreX must read
    overview rows. This filter is intentionally applied before grouping or database
    persistence: unrelated posts are thrown away immediately.
    """

    subject_tokens = set(_tokens(subject))
    title_tokens = _tokens(request.title)
    if not title_tokens:
        return False

    significant = tuple(token for token in title_tokens if token not in {"a", "an", "the", "of", "and", "to"})
    required = significant or title_tokens
    matched = sum(1 for token in required if token in subject_tokens)

    # Short titles need an exact token match; longer titles tolerate one missing
    # token because Usenet release names frequently abbreviate punctuation/subtitles.
    minimum = len(required) if len(required) <= 2 else max(2, len(required) - 1)
    return matched >= minimum


def scan_requested_book_group(
    provider: NntpProvider,
    group: NntpProviderGroup,
    repository,
    request: BookSearchRequest,
    *,
    client_factory: Callable[[NntpProvider], _TargetedClient] = _default_client_factory,
    max_windows: int = 8,
) -> TargetedScanStats:
    """Search newest-to-oldest overview windows for one requested book only.

    Unlike the continuous scanner, this path never reads or advances the durable
    provider/group checkpoint. Only overview rows matching the requested title are
    handed to the audiobook classifier/indexer; every unrelated header is discarded.
    """

    if max_windows < 1:
        raise ValueError("max_windows must be at least 1")
    max_windows = min(int(max_windows), 200)

    windows_scanned = 0
    headers_examined = 0
    matching_headers: list[ArticleHeader] = []

    with client_factory(provider) as client:
        if provider.username is not None or provider.password is not None:
            if provider.username is None or provider.password is None:
                raise ValueError("NNTP username and password must be configured together")
            client.authenticate(provider.username, provider.password)

        info = client.group(group.group_name)
        window_end = info.high

        for _ in range(max_windows):
            if window_end < info.low:
                break
            window_start = max(info.low, window_end - group.scan_batch_size + 1)
            rows = list(client.xover(window_start, window_end))
            windows_scanned += 1
            headers_examined += len(rows)

            window_matches = [
                ArticleHeader(
                    message_id=row.message_id,
                    subject=row.subject,
                    bytes=row.bytes,
                    group=group.group_name,
                )
                for row in rows
                if subject_matches_request(row.subject, request)
            ]
            matching_headers.extend(window_matches)
            if window_matches:
                break
            window_end = window_start - 1

    if not matching_headers:
        return TargetedScanStats(
            windows_scanned=windows_scanned,
            headers_examined=headers_examined,
        )

    indexing = index_batches(
        [IndexBatch(headers=matching_headers)],
        repository,
        batch_size=max(1, min(group.scan_batch_size, 512)),
        max_pending_groups=max(1, min(len(matching_headers), 4096)),
    )
    return TargetedScanStats(
        windows_scanned=windows_scanned,
        headers_examined=headers_examined,
        headers_matched=len(matching_headers),
        releases_indexed=indexing.releases_indexed,
        releases_rejected=indexing.releases_rejected,
        duplicate_releases=indexing.duplicate_releases,
    )


def acquire_requested_book(
    provider_repository,
    release_repository,
    request: BookSearchRequest,
    *,
    client_factory: Callable[[NntpProvider], _TargetedClient] | None = None,
    max_windows: int = 8,
) -> TargetedAcquisitionStats:
    """Search enabled audiobook groups and retain only headers for this request."""

    totals = TargetedAcquisitionStats()
    for provider in provider_repository.list_enabled():
        for group in provider.groups:
            if not group.enabled:
                continue
            kwargs = {"max_windows": max_windows}
            if client_factory is not None:
                kwargs["client_factory"] = client_factory
            stats = scan_requested_book_group(
                provider,
                group,
                release_repository,
                request,
                **kwargs,
            )
            totals = TargetedAcquisitionStats(
                groups_searched=totals.groups_searched + 1,
                windows_scanned=totals.windows_scanned + stats.windows_scanned,
                headers_examined=totals.headers_examined + stats.headers_examined,
                headers_matched=totals.headers_matched + stats.headers_matched,
                releases_indexed=totals.releases_indexed + stats.releases_indexed,
                releases_rejected=totals.releases_rejected + stats.releases_rejected,
                duplicate_releases=totals.duplicate_releases + stats.duplicate_releases,
            )
    return totals
