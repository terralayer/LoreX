from __future__ import annotations

from lorex.downloader.provider import ProviderConfig, ProviderSet


def test_provider_order_is_deterministic_for_equal_priority() -> None:
    providers = ProviderSet([
        ProviderConfig("zeta", "z.example", priority=10),
        ProviderConfig("alpha", "a.example", priority=10),
    ])

    assert [provider.name for provider in providers.ordered()] == ["alpha", "zeta"]
