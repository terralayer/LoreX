from pathlib import Path


def test_docker_image_bundles_and_runs_migrations_before_uvicorn() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "COPY alembic.ini ./alembic.ini" in dockerfile
    assert "COPY migrations/ ./migrations/" in dockerfile
    assert "alembic upgrade head" in dockerfile
    assert dockerfile.index("alembic upgrade head") < dockerfile.index("uvicorn lorex.main:app")
