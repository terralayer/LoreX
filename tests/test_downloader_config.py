from __future__ import annotations

from pathlib import Path

import pytest

from lorex.downloader.engine import DownloaderConfig


def test_downloader_config_rejects_unbounded_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_active_articles"):
        DownloaderConfig(download_root=tmp_path, max_active_articles=0)
    with pytest.raises(ValueError, match="progress_byte_threshold"):
        DownloaderConfig(download_root=tmp_path, progress_byte_threshold=0)
    with pytest.raises(ValueError, match="progress_time_threshold_seconds"):
        DownloaderConfig(download_root=tmp_path, progress_time_threshold_seconds=0)
