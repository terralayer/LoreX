from __future__ import annotations

import importlib.util
from pathlib import Path


def test_postgres_persistence_foundation_exists():
    assert importlib.util.find_spec("lorex.db") is not None
    assert importlib.util.find_spec("lorex.db_models") is not None
    assert Path("alembic.ini").is_file()
    assert Path("migrations/versions/0001_postgres_persistence.py").is_file()
