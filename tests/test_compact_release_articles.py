from __future__ import annotations

import os

import pytest
from sqlalchemy import inspect, text

from lorex.db import create_engine_from_url, session_factory
from lorex.domain import ArticleHeader, IndexedRelease
from lorex.postgres_repository import PostgresReleaseRepository


@pytest.fixture()
def database():
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE release_articles, indexer_checkpoints, releases RESTART IDENTITY CASCADE"))
    repository = PostgresReleaseRepository(session_factory(engine))
    yield repository, engine
    engine.dispose()


def _release() -> IndexedRelease:
    return IndexedRelease(
        id="compact-release",
        title="Project Hail Mary",
        author="Andy Weir",
        narrator="Ray Porter",
        format="archive",
        size=200,
        completion=1.0,
        nzb="",
        source_subject="Project Hail Mary.archive",
    )


def test_real_yenc_segments_share_one_compact_payload_row(database):
    repository, engine = database
    articles = (
        ArticleHeader(
            "<one@test>",
            'poster prefix "Project.Hail.Mary.part01.rar" yEnc (1/2)',
            100,
            "alt.binaries.audiobooks",
        ),
        ArticleHeader(
            "<two@test>",
            'poster prefix "Project.Hail.Mary.part01.rar" yEnc (2/2)',
            100,
            "alt.binaries.audiobooks",
        ),
    )

    assert repository.commit_index_batch([(_release(), articles)]) == 1

    schema = inspect(engine)
    assert "release_payloads" in schema.get_table_names()
    assert "payload_id" in {column["name"] for column in schema.get_columns("release_articles")}

    with engine.connect() as connection:
        payloads = connection.execute(
            text(
                "SELECT id, release_id, filename, \"group\" "
                "FROM release_payloads WHERE release_id = :release_id"
            ),
            {"release_id": "compact-release"},
        ).mappings().all()
        stored_articles = connection.execute(
            text(
                "SELECT payload_id, message_id, subject, \"group\", bytes "
                "FROM release_articles WHERE release_id = :release_id ORDER BY id"
            ),
            {"release_id": "compact-release"},
        ).mappings().all()

    assert len(payloads) == 1
    assert payloads[0]["filename"] == "Project.Hail.Mary.part01.rar"
    assert payloads[0]["group"] == "alt.binaries.audiobooks"
    assert [row["payload_id"] for row in stored_articles] == [payloads[0]["id"], payloads[0]["id"]]
    assert [row["subject"] for row in stored_articles] == [None, None]
    assert [row["group"] for row in stored_articles] == [None, None]

    restored = repository.get_articles("compact-release")
    assert [item.message_id for item in restored] == ["<one@test>", "<two@test>"]
    assert [item.bytes for item in restored] == [100, 100]
    assert [item.group for item in restored] == ["alt.binaries.audiobooks", "alt.binaries.audiobooks"]
    assert all("Project.Hail.Mary.part01.rar" in item.subject for item in restored)


def test_ambiguous_legacy_subjects_remain_lossless(database):
    repository, engine = database
    articles = (
        ArticleHeader("<legacy-one@test>", "Author - Book.m4b [1/2]", 100),
        ArticleHeader("<legacy-two@test>", "Author - Book.m4b [2/2]", 100),
    )
    release = IndexedRelease(
        id="legacy-compatible",
        title="Book",
        author="Author",
        narrator=None,
        format="m4b",
        size=200,
        completion=1.0,
        nzb="",
        source_subject="Author - Book.m4b",
    )

    assert repository.commit_index_batch([(release, articles)]) == 1
    assert repository.get_articles(release.id) == articles

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT payload_id, subject, \"group\" "
                "FROM release_articles WHERE release_id = :release_id ORDER BY id"
            ),
            {"release_id": release.id},
        ).mappings().all()

    assert [row["payload_id"] for row in rows] == [None, None]
    assert [row["subject"] for row in rows] == [item.subject for item in articles]
