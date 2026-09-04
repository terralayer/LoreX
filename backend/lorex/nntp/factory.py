from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from lorex.downloader.engine import DownloaderConfig, StreamingDownloader
from lorex.downloader.provider import ProviderConfig, ProviderSet
from lorex.nntp.article_provider import NntpArticleProvider
from lorex.nntp.errors import NntpConfigurationError
from lorex.nntp.models import NntpProvider


class _NullDownloadState:
    def pending_articles(self, job_id, articles):
        return tuple(articles)

    def mark_article_started(self, *args, **kwargs):
        return None

    def mark_article_completed(self, *args, **kwargs):
        return None

    def mark_article_failed(self, *args, **kwargs):
        return None

    def persist_job_progress(self, *args, **kwargs):
        return None

    def mark_completed(self, *args, **kwargs):
        return None

    def mark_failed(self, *args, **kwargs):
        return None

    def record_provider_attempt(self, *args, **kwargs):
        return None


def build_provider_set(
    provider_repository,
    *,
    client_factory: Callable[[NntpProvider], object] | None = None,
) -> ProviderSet:
    providers = list(provider_repository.list_enabled())
    if not providers:
        raise NntpConfigurationError("No enabled NNTP providers are configured")
    configs: list[ProviderConfig] = []
    clients = {}
    for provider in providers:
        config = ProviderConfig(
            name=provider.name,
            host=provider.host,
            port=provider.port,
            priority=provider.priority,
            fill_server=provider.fill_server,
            max_connections=provider.max_connections,
            enabled=provider.enabled,
            tls=True,
        )
        configs.append(config)
        clients[provider.name] = NntpArticleProvider(
            provider,
            client_factory=client_factory,
        )
    return ProviderSet(configs, clients=clients)


def build_live_downloader(
    provider_repository,
    *,
    state: Any | None = None,
    root: str | Path = "/downloads",
    max_active_articles: int = 8,
    client_factory: Callable[[NntpProvider], object] | None = None,
) -> StreamingDownloader:
    providers = build_provider_set(
        provider_repository,
        client_factory=client_factory,
    )
    return StreamingDownloader(
        providers,
        state or _NullDownloadState(),
        DownloaderConfig(download_root=Path(root), max_active_articles=max_active_articles),
    )
