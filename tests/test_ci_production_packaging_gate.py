from pathlib import Path


def test_ci_builds_production_image_and_validates_compose() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "docker build -t lorex-ci ." in workflow
    assert "docker compose config" in workflow
