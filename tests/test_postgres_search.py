from __future__ import annotations

import importlib.util

from lorex.postgres_repository import PostgresReleaseRepository


def test_paged_search_contract_exists():
    assert importlib.util.find_spec("lorex.search") is not None
    assert hasattr(PostgresReleaseRepository, "search_page")
