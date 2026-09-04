from __future__ import annotations

import pytest

from lorex.nntp.client import NntpClient
from lorex.nntp.errors import NntpArticleMissing, NntpAuthenticationError
from tests.support.fake_nntp import FakeNntpServer


def test_tls_auth_group_xover_and_body_streaming():
    with FakeNntpServer() as server:
        client = NntpClient(
            "localhost",
            server.port,
            ssl_context=server.client_context,
            timeout=3.0,
            body_chunk_size=8,
        )
        with client:
            client.authenticate("fixture-user", "fixture-value")
            group = client.group("alt.binaries.audiobooks")
            assert (group.low, group.high) == (100, 200)
            rows = list(client.xover(101, 101))
            assert len(rows) == 1
            assert rows[0].article_number == 101
            assert rows[0].message_id == "<101@test>"
            assert rows[0].bytes == 1234
            chunks = list(client.body("<101@test>"))
            assert chunks
            assert max(map(len, chunks)) <= 8
            assert b"".join(chunks) == b"first\r\n.second\r\nthird\r\n"

    assert "AUTHINFO USER fixture-user" in server.commands
    assert "AUTHINFO PASS fixture-value" in server.commands
    assert "GROUP alt.binaries.audiobooks" in server.commands
    assert "XOVER 101-101" in server.commands
    assert "BODY <101@test>" in server.commands


def test_xover_falls_back_to_over_once():
    with FakeNntpServer() as server:
        server.require_auth = False
        server.support_xover = False
        client = NntpClient("localhost", server.port, ssl_context=server.client_context, timeout=3.0)
        with client:
            assert list(client.xover(101, 101))[0].article_number == 101
            assert list(client.xover(101, 101))[0].article_number == 101
    assert server.commands.count("XOVER 101-101") == 1
    assert server.commands.count("OVER 101-101") == 2


def test_auth_failure_is_classified_without_echoing_secret():
    with FakeNntpServer() as server:
        server.auth_ok = False
        client = NntpClient("localhost", server.port, ssl_context=server.client_context, timeout=3.0)
        with client:
            with pytest.raises(NntpAuthenticationError) as caught:
                client.authenticate("fixture-user", "fixture-value")
    assert "fixture-value" not in str(caught.value)


def test_missing_body_is_classified():
    with FakeNntpServer() as server:
        server.require_auth = False
        client = NntpClient("localhost", server.port, ssl_context=server.client_context, timeout=3.0)
        with client:
            with pytest.raises(NntpArticleMissing):
                list(client.body("<missing@test>"))


def test_command_arguments_reject_line_injection():
    with FakeNntpServer() as server:
        client = NntpClient("localhost", server.port, ssl_context=server.client_context, timeout=3.0)
        with client:
            with pytest.raises(ValueError):
                client.group("alt.binaries.audiobooks\r\nQUIT")
