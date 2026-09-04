from __future__ import annotations

from base64 import urlsafe_b64encode
import os
from pathlib import Path
import zlib

from sqlalchemy import text

from lorex.db import create_engine_from_url, session_factory
from lorex.domain import DownloadJob
from lorex.library.importer import LibraryImporter
from lorex.nntp.client import NntpClient
from lorex.nntp.factory import build_live_downloader
from lorex.nntp.models import NntpProviderGroup
from lorex.nntp.repository import PostgresNntpProviderRepository
from lorex.nntp.scanner import scan_group_once
from lorex.postgres_repository import PostgresJobRepository, PostgresLibraryRepository, PostgresReleaseRepository
from lorex.security.credentials import CredentialCipher
from tests.support.fake_nntp import FakeNntpServer


def _cipher() -> CredentialCipher:
    key = urlsafe_b64encode(b"e" * 32).decode().rstrip("=")
    return CredentialCipher.from_base64url(key)


def _reset_db(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE provider_health, download_articles, download_jobs, library_books, "
                "release_articles, indexer_checkpoints, releases, nntp_provider_groups, nntp_providers "
                "RESTART IDENTITY CASCADE"
            )
        )


def _yenc(payload: bytes) -> bytes:
    encoded_lines: list[bytes] = []
    line = bytearray()
    for value in payload:
        shifted = (value + 42) & 0xFF
        token = bytes((61, (shifted + 64) & 0xFF)) if shifted in {0, 9, 10, 13, 61} else bytes((shifted,))
        if line and len(line) + len(token) > 128:
            encoded_lines.append(bytes(line))
            line.clear()
        line.extend(token)
    if line:
        encoded_lines.append(bytes(line))
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    return b"\r\n".join(
        [
            f"=ybegin line=128 size={len(payload)} name=fixture.bin".encode(),
            *encoded_lines,
            f"=yend size={len(payload)} crc32={crc:08x}".encode(),
        ]
    )


def test_fake_tls_scan_primary_fill_download_and_library_import(tmp_path: Path):
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    _reset_db(engine)
    sessions = session_factory(engine)
    providers = PostgresNntpProviderRepository(sessions, _cipher())
    releases = PostgresReleaseRepository(sessions)
    jobs = PostgresJobRepository(sessions)
    library = PostgresLibraryRepository(sessions)

    part1 = b"m4b-fixture-part-one-" * 2048
    part2 = b"m4b-fixture-part-two-" * 2048

    with FakeNntpServer() as primary_server, FakeNntpServer() as fill_server:
        primary_server.low = 101
        primary_server.high = 102
        primary_server.overview_rows = [
            f"101\tAndy Weir - Project Hail Mary - Ray Porter.m4b [1/2]\tposter\tdate\t<101@lorex.test>\t\t{len(part1)}\t10",
            f"102\tAndy Weir - Project Hail Mary - Ray Porter.m4b [2/2]\tposter\tdate\t<102@lorex.test>\t\t{len(part2)}\t10",
        ]
        primary_server.bodies = {"<101@lorex.test>": _yenc(part1)}
        fill_server.bodies = {"<102@lorex.test>": _yenc(part2)}

        group = NntpProviderGroup("alt.binaries.audiobooks", scan_batch_size=500)
        primary = providers.create(
            name="Primary",
            host="localhost",
            port=primary_server.port,
            priority=10,
            max_connections=2,
            username="fixture-user",
            password="fixture-value",
            groups=[group],
        )
        providers.create(
            name="Fill",
            host="localhost",
            port=fill_server.port,
            priority=200,
            fill_server=True,
            max_connections=1,
            username="fixture-user",
            password="fixture-value",
            groups=[group],
        )

        ssl_contexts = {
            primary_server.port: primary_server.client_context,
            fill_server.port: fill_server.client_context,
        }

        def client_factory(provider):
            return NntpClient(
                provider.host,
                provider.port,
                ssl_context=ssl_contexts[provider.port],
                timeout=2.0,
                body_chunk_size=4096,
            )

        stats = scan_group_once(primary, group, releases, client_factory=client_factory, mode="backfill")
        assert stats.headers_received == 2
        assert stats.releases_indexed == 1

        found = releases.search("Project Hail Mary")
        assert len(found) == 1
        release = found[0]
        articles = releases.get_articles(release.id)
        assert [article.message_id for article in articles] == ["<101@lorex.test>", "<102@lorex.test>"]

        job = jobs.add(DownloadJob(id="livee2ejob01", release_id=release.id))
        downloader = build_live_downloader(
            providers,
            state=jobs,
            root=tmp_path / "downloads",
            max_active_articles=2,
            client_factory=client_factory,
        )
        result = downloader.download_job(job, release, articles)
        book = LibraryImporter(library, root=str(tmp_path / "library")).import_download(result)

        completed = sorted((tmp_path / "downloads" / job.id).glob("*.complete"))
        assert len(completed) == 2
        assert {item.read_bytes() for item in completed} == {part1, part2}
        assert book.title == "Project Hail Mary"
        assert book.author == "Andy Weir"
        assert book.narrator == "Ray Porter"
        assert library.all()[0].id == book.id
        assert any(command == "BODY <102@lorex.test>" for command in primary_server.commands)
        assert any(command == "BODY <102@lorex.test>" for command in fill_server.commands)

    engine.dispose()
