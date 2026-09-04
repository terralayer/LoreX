from pathlib import Path


def test_scanner_runs_continuously_in_compose() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert 'command: ["python", "-m", "lorex.workers.nntp_scanner", "--mode", "live"]' in compose
    assert 'restart: unless-stopped' in compose
    assert '"--once"' not in compose
