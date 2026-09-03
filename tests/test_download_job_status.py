from __future__ import annotations

from lorex.domain import DownloadJob


def test_download_job_default_status_remains_queued() -> None:
    assert DownloadJob("job-1", "release-1").status == "queued"
