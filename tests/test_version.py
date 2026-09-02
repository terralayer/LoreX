from __future__ import annotations

import json
import tomllib
from pathlib import Path

from lorex.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_approved_alpha_version_is_consistent_across_packages_ui_and_api() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_json = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    package_init = (ROOT / "backend/lorex/__init__.py").read_text(encoding="utf-8")
    app_source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")

    assert pyproject["project"]["version"] == "0.1.1a1"
    assert package_json["version"] == "0.1.1-alpha.1"
    assert '__version__ = "0.1.1a1"' in package_init
    assert "v0.1.1 alpha" in app_source
    assert create_app().version == "0.1.1 alpha"
