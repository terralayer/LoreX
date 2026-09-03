from __future__ import annotations

from lorex.downloader.provider import ProviderConfig, ProviderSet


def test_disabled_providers_are_excluded_from_order() -> None:
    providers = ProviderSet([
        ProviderConfig("disabled", "disabled.example", enabled=False),
        ProviderConfig("enabled", "enabled.example", priority=20),
    ])

    assert [provider.name for provider in providers.ordered()] == ["enabled"]
