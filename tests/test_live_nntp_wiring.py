from __future__ import annotations

from types import SimpleNamespace

import pytest

from lorex.downloader.engine import StreamingDownloader
from lorex.nntp.errors import NntpConfigurationError
from lorex.nntp.factory import build_live_downloader, build_provider_set
from lorex.nntp.models import NntpProvider, NntpProviderGroup
from lorex.workers.nntp_scanner import run_once


class ProviderRepo:
    def __init__(self, providers):
        self.providers = list(providers)

    def list_enabled(self):
        return list(self.providers)


def _provider(name="Primary", *, fill=False, priority=10):
    return NntpProvider(
        id=("a" if not fill else "b") * 32,
        name=name,
        host=f"{name.lower()}.example.test",
        port=563,
        enabled=True,
        priority=priority,
        fill_server=fill,
        max_connections=3,
        username="fixture-user",
        password="fixture-value",
        groups=(NntpProviderGroup("alt.binaries.audiobooks", scan_batch_size=500),),
    )


def test_provider_factory_preserves_priority_fill_and_connection_limits(tmp_path):
    primary = _provider()
    fill = _provider("Fill", fill=True, priority=200)
    provider_set = build_provider_set(ProviderRepo([fill, primary]))

    assert provider_set.names == ("Primary", "Fill")
    assert provider_set.pool_for("Primary").config.max_connections == 3
    assert provider_set.pool_for("Fill").config.fill_server is True

    downloader = build_live_downloader(ProviderRepo([primary, fill]), root=tmp_path)
    assert isinstance(downloader, StreamingDownloader)


def test_provider_factory_fails_explicitly_when_no_enabled_provider(tmp_path):
    with pytest.raises(NntpConfigurationError):
        build_live_downloader(ProviderRepo([]), root=tmp_path)


def test_scanner_worker_once_visits_each_enabled_group(monkeypatch):
    calls = []
    providers = [_provider(), _provider("Fill", fill=True, priority=200)]

    def fake_scan(provider, group, releases, *, mode):
        calls.append((provider.name, group.group_name, mode))
        return SimpleNamespace(headers_received=1)

    monkeypatch.setattr("lorex.workers.nntp_scanner.scan_provider_group_once", fake_scan)
    count = run_once(ProviderRepo(providers), object(), mode="live")

    assert count == 2
    assert calls == [
        ("Primary", "alt.binaries.audiobooks", "live"),
        ("Fill", "alt.binaries.audiobooks", "live"),
    ]
