from pathlib import Path


def test_docker_image_bundles_and_runs_migrations_for_every_role() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    entrypoint = Path("docker-entrypoint.sh").read_text(encoding="utf-8")

    assert "COPY alembic.ini ./alembic.ini" in dockerfile
    assert "COPY migrations/ ./migrations/" in dockerfile
    assert "COPY docker-entrypoint.sh" in dockerfile
    assert 'ENTRYPOINT ["/usr/local/bin/lorex-entrypoint"]' in dockerfile
    assert "alembic upgrade head" in entrypoint
    assert 'exec "$@"' in entrypoint
