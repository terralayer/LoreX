from __future__ import annotations

import os
from pathlib import Path
import zlib

from fastapi.testclient import TestClient
from sqlalchemy import text

from lorex.db import create_engine_from_url
from lorex.library.importer import LibraryImporter
from lorex.main import create_app
from lorex.nntp.client import NntpClient
from lorex.services.download_jobs import process_next_download
from lorex.services.nntp_scanning import scan_provider_group_once
from lorex.workers.nntp_scanner import run_pass
from tests.support.fake_nntp import FakeNntpServer


def _reset_database() -> None:
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE activity_events, scanner_group_state, runtime_settings, "
                    "nntp_provider_groups, nntp_providers, provider_health, download_articles, "
                    "release_articles, indexer_checkpoints, releases, download_jobs, import_jobs, "
                    "library_books RESTART IDENTITY CASCADE"
                )
            )
    finally:
        engine.dispose()


def _yenc(payload: bytes, name: str) -> bytes:
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
            f"=ybegin line=128 size={len(payload)} name={name}".encode(),
            *encoded_lines,
            f"=yend size={len(payload)} crc32={crc:08x}".encode(),
        ]
    )


def test_full_production_flow_creates_real_library_file_without_mock_api(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LOREX_ENABLE_MOCK_API", raising=False)
    _reset_database()

    part1 = b"synthetic-m4b-part-one-" * 256
    part2 = b"synthetic-m4b-part-two-" * 256
    final_payload = part1 + part2

    with FakeNntpServer() as primary_server, FakeNntpServer() as fill_server:
        primary_server.low = 101
        primary_server.high = 102
        primary_server.overview_rows = [
            f"101\tSynthetic Author - Synthetic Book - Synthetic Narrator.m4b [1/2]\tposter\tdate\t<101@production.test>\t\t{len(part1)}\t10",
            f"102\tSynthetic Author - Synthetic Book - Synthetic Narrator.m4b [2/2]\tposter\tdate\t<102@production.test>\t\t{len(part2)}\t10",
        ]
        primary_server.bodies = {"<101@production.test>": _yenc(part1, "Synthetic Book.m4b")}
        fill_server.bodies = {"<102@production.test>": _yenc(part2, "Synthetic Book.m4b")}

        contexts = {
            primary_server.port: primary_server.client_context,
            fill_server.port: fill_server.client_context,
        }

        def client_factory(provider):
            return NntpClient(
                provider.host,
                provider.port,
                ssl_context=contexts[provider.port],
                timeout=2.0,
                body_chunk_size=4096,
            )

        app = create_app()
        with TestClient(app) as client:
            container = client.app.state.container
            container.nntp_client_factory = client_factory
            container.download_root = str(tmp_path / "downloads")
            container.importer = LibraryImporter(container.library, root=str(tmp_path / "library"))

            primary = client.post(
                "/api/settings/nntp/providers",
                json={
                    "name": "Synthetic Primary",
                    "host": "localhost",
                    "port": primary_server.port,
                    "enabled": True,
                    "priority": 10,
                    "fill_server": False,
                    "max_connections": 2,
                    "username": "fixture-user",
                    "password": "fixture-value",
                    "groups": [
                        {
                            "group_name": "alt.binaries.audiobooks",
                            "enabled": True,
                            "scan_batch_size": 500,
                            "backfill_days": 0,
                        }
                    ],
                },
            )
            assert primary.status_code == 201
            primary_payload = primary.json()
            assert primary_payload["username_configured"] is True
            assert primary_payload["password_configured"] is True
            assert "username" not in primary_payload
            assert "password" not in primary_payload

            fill = client.post(
                "/api/settings/nntp/providers",
                json={
                    "name": "Synthetic Fill",
                    "host": "localhost",
                    "port": fill_server.port,
                    "enabled": True,
                    "priority": 200,
                    "fill_server": True,
                    "max_connections": 1,
                    "username": "fixture-user",
                    "password": "fixture-value",
                    "groups": [],
                },
            )
            assert fill.status_code == 201

            tested = client.post(f"/api/settings/nntp/providers/{primary_payload['id']}/test")
            assert tested.status_code == 200
            assert tested.json()["status"] == "ok"

            def scan_fn(provider, group, repository, *, mode="live"):
                return scan_provider_group_once(
                    provider,
                    group,
                    repository,
                    client_factory=client_factory,
                    mode=mode,
                )

            scanned = run_pass(
                container.nntp_providers,
                container.releases,
                container.runtime,
                mode="backfill",
                scan_fn=scan_fn,
            )
            assert scanned == 1

            search = client.get("/api/releases/search", params={"q": "Synthetic Book"})
            assert search.status_code == 200
            assert search.json()["total"] == 1
            release = search.json()["results"][0]

            grabbed = client.post(f"/api/releases/{release['id']}/grab")
            assert grabbed.status_code == 200
            assert grabbed.json()["status"] == "queued"

            processed = process_next_download(container, worker_id="production-e2e-worker")
            assert processed is not None
            assert processed.status == "completed"

            final_file = tmp_path / "library" / "Synthetic Author" / "Synthetic Book" / "Synthetic Book.m4b"
            assert final_file.is_file()
            assert final_file.read_bytes() == final_payload

            library = client.get("/api/library/books", params={"q": "Synthetic Book"})
            assert library.status_code == 200
            assert library.json()["total"] == 1
            assert library.json()["results"][0]["size"] == len(final_payload)

            summary = client.get("/api/system/summary")
            assert summary.status_code == 200
            summary_payload = summary.json()
            assert summary_payload["ready"] is True
            assert summary_payload["library_books"] == 1
            assert summary_payload["total_releases"] == 1
            assert summary_payload["downloads"]["completed"] == 1

            activity = client.get("/api/activity", params={"limit": 50})
            messages = [event["message"] for event in activity.json()["events"]]
            assert any(message.startswith("Scanned Synthetic Primary") for message in messages)
            assert any(message.startswith("Completed download and import") for message in messages)

            mock = client.post(
                "/api/index/mock",
                json={
                    "headers": [
                        {
                            "message_id": "<forbidden-mock@test>",
                            "subject": "Forbidden Mock.m4b [1/1]",
                            "bytes": 1,
                        }
                    ]
                },
            )
            assert mock.status_code == 404

            assert any(command == "BODY <102@production.test>" for command in primary_server.commands)
            assert any(command == "BODY <102@production.test>" for command in fill_server.commands)
