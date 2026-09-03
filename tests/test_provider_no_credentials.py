from __future__ import annotations

from lorex.downloader.provider import ProviderConfig


def test_provider_config_repr_contains_no_credentials_fields() -> None:
    config = ProviderConfig(name="primary", host="news.example")

    rendered = repr(config).casefold()
    assert "password" not in rendered
    assert "username" not in rendered
