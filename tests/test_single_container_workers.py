from pathlib import Path


def test_default_container_entrypoint_starts_embedded_workers() -> None:
    entrypoint = Path("docker-entrypoint.sh").read_text(encoding="utf-8")

    assert "LOREX_EMBEDDED_WORKERS" in entrypoint
    assert "lorex.workers.nntp_scanner" in entrypoint
    assert "lorex.workers.download_worker" in entrypoint


def test_compose_api_disables_embedded_workers_because_compose_runs_dedicated_workers() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert 'LOREX_EMBEDDED_WORKERS: "0"' in compose
    assert "nntp-scanner:" in compose
    assert "download-worker:" in compose
