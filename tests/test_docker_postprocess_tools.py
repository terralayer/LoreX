from pathlib import Path


def test_docker_image_bundles_required_postprocess_tools() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "apt-get update" in dockerfile
    assert "par2" in dockerfile
    assert "7zip" in dockerfile
    assert "unar" in dockerfile
    assert "ffmpeg" in dockerfile
    assert "rm -rf /var/lib/apt/lists/*" in dockerfile
