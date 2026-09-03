from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from sqlalchemy import text

from lorex.db import create_engine_from_url


def test_postgres_persistence_foundation_exists():
    assert importlib.util.find_spec("lorex.db") is not None
    assert importlib.util.find_spec("lorex.db_models") is not None
    assert Path("alembic.ini").is_file()
    assert Path("migrations/versions/0001_postgres_persistence.py").is_file()


def test_release_search_trigram_indexes_exist():
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    try:
        with engine.connect() as connection:
            extensions = set(connection.execute(text("SELECT extname FROM pg_extension")).scalars())
            indexes = set(
                connection.execute(
                    text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'releases'")
                ).scalars()
            )
    finally:
        engine.dispose()

    assert "pg_trgm" in extensions
    assert {
        "ix_releases_normalized_title_trgm",
        "ix_releases_normalized_author_trgm",
        "ix_releases_narrator_trgm",
        "ix_releases_source_subject_trgm",
    } <= indexes
