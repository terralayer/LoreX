from __future__ import annotations

import importlib.util


def test_postgres_release_repository_exists():
    assert importlib.util.find_spec("lorex.postgres_repository") is not None
