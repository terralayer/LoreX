from __future__ import annotations

import threading
import time
import zlib

import pytest

from lorex.downloader.provider import ArticleUnavailable, ProviderConfig, ProviderSet, ProviderTemporaryError
from lorex.nntp.article_provider import NntpArticleProvider
from lorex.nntp.errors import NntpArticleMissing, NntpAuthenticationError, NntpTemporaryError
from lorex.nntp.models import NntpProvider


def _provider(name: str = "Primary") -> NntpProvider:
    return NntpProvider(
        id="c" * 32,
        name=name,
        host="news.example.test",
        username="fixture-user",
        password="fixture-value",
        max_connections=1,
    )


def _yenc(payload: bytes) -> list[bytes]:
    lines: list[bytes] = []
    line = bytearray()
    for value in payload:
        shifted = (value + 42) & 0xFF
        token = bytes((61, (shifted + 64) & 0xFF)) if shifted in {0, 9, 10, 13, 61} else bytes((shifted,))
        if line and len(line) + len(token) > 128:
            lines.append(bytes(line) + b"\r\n")
            line.clear()
        line.extend(token)
    if line:
        lines.append(bytes(line) + b"\r\n")
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    return [
        f"=ybegin line=128 size={len(payload)} name=fixture.bin\r\n".encode(),
        *lines,
        f"=yend size={len(payload)} crc32={crc:08x}\r\n".encode(),
    ]


class ScriptedClient:
    def __init__(self, chunks=None, error: Exception | None = None) -> None:
        self.chunks = list(chunks or [])
        self.error = error
        self.authenticated = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def authenticate(self, username: str, password: str) -> None:
        self.authenticated = (username, password)
        if isinstance(self.error, NntpAuthenticationError):
            raise self.error

    def body(self, message_id: str):
        if self.error is not None and not isinstance(self.error, NntpAuthenticationError):
            raise self.error
        yield from self.chunks


def test_yenc_body_is_decoded_incrementally_to_payload():
    payload = (b"LoreX-audio-fixture-" * 8000) + bytes(range(256))
    client = ScriptedClient(_yenc(payload))
    provider = NntpArticleProvider(_provider(), client_factory=lambda _: client, output_chunk_size=4096)

    chunks = list(provider.stream_article("<fixture@test>"))

    assert b"".join(chunks) == payload
    assert chunks
    assert max(map(len, chunks)) <= 4096
    assert client.authenticated == ("fixture-user", "fixture-value")


def test_plain_unencoded_body_is_passed_through_exactly():
    chunks = [b"plain line one\r\n", b"plain line two\r\n"]
    provider = NntpArticleProvider(_provider(), client_factory=lambda _: ScriptedClient(chunks))
    assert b"".join(provider.stream_article("<fixture@test>")) == b"".join(chunks)


def test_missing_article_maps_to_downloader_unavailable():
    provider = NntpArticleProvider(
        _provider(),
        client_factory=lambda _: ScriptedClient(error=NntpArticleMissing("missing")),
    )
    with pytest.raises(ArticleUnavailable):
        list(provider.stream_article("<missing@test>"))


def test_temporary_transport_error_maps_to_downloader_temporary_error():
    provider = NntpArticleProvider(
        _provider(),
        client_factory=lambda _: ScriptedClient(error=NntpTemporaryError("temporary")),
    )
    with pytest.raises(ProviderTemporaryError):
        list(provider.stream_article("<temporary@test>"))


def test_authentication_error_is_not_misreported_as_missing_article():
    provider = NntpArticleProvider(
        _provider(),
        client_factory=lambda _: ScriptedClient(error=NntpAuthenticationError("auth")),
    )
    with pytest.raises(NntpAuthenticationError):
        list(provider.stream_article("<fixture@test>"))


def test_primary_missing_falls_through_to_fill_provider():
    primary = _provider("Primary")
    fill = NntpProvider(
        id="d" * 32,
        name="Fill",
        host="fill.example.test",
        username="fixture-user",
        password="fixture-value",
        fill_server=True,
        priority=200,
    )
    provider_set = ProviderSet(
        [
            ProviderConfig(name="Primary", host=primary.host, priority=10),
            ProviderConfig(name="Fill", host=fill.host, priority=200, fill_server=True),
        ],
        clients={
            "Primary": NntpArticleProvider(
                primary, client_factory=lambda _: ScriptedClient(error=NntpArticleMissing("missing"))
            ),
            "Fill": NntpArticleProvider(fill, client_factory=lambda _: ScriptedClient([b"payload\r\n"])),
        },
    )

    assert b"".join(provider_set.stream_with_fallback("<fixture@test>")) == b"payload\r\n"


def test_provider_pool_connection_limit_is_preserved():
    provider = _provider()
    active = 0
    peak = 0
    lock = threading.Lock()

    class SlowClient(ScriptedClient):
        def body(self, message_id: str):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                time.sleep(0.03)
                yield b"payload\r\n"
            finally:
                with lock:
                    active -= 1

    article_provider = NntpArticleProvider(provider, client_factory=lambda _: SlowClient())
    provider_set = ProviderSet(
        [ProviderConfig(name=provider.name, host=provider.host, max_connections=1)],
        clients={provider.name: article_provider},
    )

    threads = [
        threading.Thread(target=lambda: list(provider_set.pool_for(provider.name).stream_article(f"<{i}@test>")))
        for i in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak == 1
