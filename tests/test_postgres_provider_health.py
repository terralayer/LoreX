from __future__ import annotations

import os

from lorex.db import create_engine_from_url, session_factory
from lorex.postgres_repository import PostgresJobRepository


def test_postgres_provider_health_aggregates_updates() -> None:
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    repository = PostgresJobRepository(session_factory(engine))
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("TRUNCATE provider_health RESTART IDENTITY CASCADE")
        repository.record_provider_attempt("primary", success=True, fallback=False, byte_count=100, elapsed_ms=10.0)
        repository.record_provider_attempt("primary", success=False, fallback=True, byte_count=0, elapsed_ms=5.0)
        snapshot = repository.provider_health("primary")
        assert snapshot.attempts == 2
        assert snapshot.successes == 1
        assert snapshot.failures == 1
        assert snapshot.fallbacks == 1
        assert snapshot.bytes_delivered == 100
        assert snapshot.elapsed_ms_total == 15.0
    finally:
        engine.dispose()
