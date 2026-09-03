from __future__ import annotations

import os

from sqlalchemy import inspect

from lorex.db import create_engine_from_url


def test_download_efficiency_schema_exists() -> None:
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    try:
        inspector = inspect(engine)
        assert "download_articles" in inspector.get_table_names()
        assert "provider_health" in inspector.get_table_names()

        job_columns = {column["name"] for column in inspector.get_columns("download_jobs")}
        assert {
            "claimed_at",
            "claimed_by",
            "bytes_completed",
            "articles_completed",
            "updated_at",
        } <= job_columns

        article_columns = {column["name"] for column in inspector.get_columns("download_articles")}
        assert {
            "job_id",
            "message_id",
            "status",
            "bytes_completed",
            "provider",
            "attempts",
            "created_order",
            "updated_at",
        } <= article_columns

        health_columns = {column["name"] for column in inspector.get_columns("provider_health")}
        assert {
            "provider",
            "attempts",
            "successes",
            "failures",
            "fallbacks",
            "bytes_delivered",
            "elapsed_ms_total",
        } <= health_columns
    finally:
        engine.dispose()
