from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from lorex.db import create_engine_from_url, session_factory
from lorex.domain import ArticleHeader, IndexCheckpoint, IndexedRelease
from lorex.postgres_repository import PostgresReleaseRepository


@pytest.fixture()
def repository():
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE release_articles, indexer_checkpoints, releases RESTART IDENTITY CASCADE"))
    repo = PostgresReleaseRepository(session_factory(engine))
    yield repo
    engine.dispose()


def _release(release_id: str = "release-1") -> IndexedRelease:
    return IndexedRelease(
        id=release_id,
        title="Project Hail Mary",
        author="Andy Weir",
        narrator="Ray Porter",
        format="m4b",
        size=123456,
        completion=1.0,
        nzb="",
        source_subject="Andy Weir - Project Hail Mary - Ray Porter.m4b",
    )


def _articles() -> tuple[ArticleHeader, ...]:
    return (
        ArticleHeader("<one@test>", "Andy Weir - Project Hail Mary - Ray Porter.m4b [1/2]", 60000),
        ArticleHeader("<two@test>", "Andy Weir - Project Hail Mary - Ray Porter.m4b [2/2]", 63456),
    )


def test_commit_batch_persists_release_articles_and_checkpoint(repository):
    checkpoint = IndexCheckpoint("backfill", "alt.binaries.audiobooks", 1000)

    inserted = repository.commit_index_batch([(_release(), _articles())], checkpoint)

    assert inserted == 1
    assert repository.get("release-1") == _release()
    assert repository.get_articles("release-1") == _articles()
    assert repository.get_checkpoint("backfill", "alt.binaries.audiobooks") == checkpoint


def test_replayed_release_is_deduplicated(repository):
    first = repository.commit_index_batch([(_release(), _articles())])
    second = repository.commit_index_batch([(_release(), _articles())])

    assert first == 1
    assert second == 0
    assert repository.get_articles("release-1") == _articles()


def test_backward_checkpoint_rolls_back_entire_batch(repository):
    repository.commit_index_batch([], IndexCheckpoint("backfill", "alt.binaries.audiobooks", 1000))

    with pytest.raises(ValueError, match="checkpoint cannot move backwards"):
        repository.commit_index_batch(
            [(_release("release-rollback"), _articles())],
            IndexCheckpoint("backfill", "alt.binaries.audiobooks", 999),
        )

    assert repository.get("release-rollback") is None
    assert repository.get_checkpoint("backfill", "alt.binaries.audiobooks") == IndexCheckpoint(
        "backfill", "alt.binaries.audiobooks", 1000
    )


def test_nzb_cache_is_durable(repository):
    repository.commit_index_batch([(_release(), _articles())])

    assert repository.get_cached_nzb("release-1") is None
    repository.cache_nzb("release-1", "<nzb />")

    assert repository.get_cached_nzb("release-1") == "<nzb />"


def test_large_release_batch_is_chunked_below_postgres_parameter_limit(repository):
    records = [(_release(f"release-{index}"), ()) for index in range(6000)]

    inserted = repository.commit_index_batch(records)

    assert inserted == 6000
    assert repository.get("release-5999") == _release("release-5999")
