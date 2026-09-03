from __future__ import annotations

import pytest

from lorex.downloader.provider import (
    ArticleUnavailable,
    ProviderConfig,
    ProviderSet,
    ProviderTemporaryError,
)


def test_provider_config_requires_tls() -> None:
    with pytest.raises(ValueError, match="TLS"):
        ProviderConfig(name="plain", host="news.example", tls=False)


def test_provider_order_places_primaries_before_fill_servers() -> None:
    providers = ProviderSet(
        [
            ProviderConfig("fill", "fill.example", priority=1, fill_server=True),
            ProviderConfig("secondary", "secondary.example", priority=20),
            ProviderConfig("primary", "primary.example", priority=10),
        ]
    )

    assert [provider.name for provider in providers.ordered()] == ["primary", "secondary", "fill"]


def test_retryable_provider_errors_fall_back_in_order() -> None:
    attempts: list[str] = []

    class FakeProvider:
        def __init__(self, name: str, error: Exception | None = None) -> None:
            self.name = name
            self.error = error

        def stream_article(self, message_id: str):
            attempts.append(self.name)
            if self.error is not None:
                raise self.error
            yield b"ok"

    providers = ProviderSet(
        [
            ProviderConfig("primary", "primary.example", priority=10),
            ProviderConfig("fill", "fill.example", priority=1, fill_server=True),
        ],
        clients={
            "primary": FakeProvider("primary", ArticleUnavailable("missing")),
            "fill": FakeProvider("fill"),
        },
    )

    chunks = list(providers.stream_with_fallback("<id>"))

    assert chunks == [b"ok"]
    assert attempts == ["primary", "fill"]


def test_temporary_provider_error_is_retryable() -> None:
    assert issubclass(ProviderTemporaryError, Exception)
