from __future__ import annotations

from lorex.domain import ImportJob


def test_import_job_defaults_to_queued_verify_stage() -> None:
    job = ImportJob(id="import-1", release_id="release-1", source_path="/downloads/job-1")

    assert job.status == "queued"
    assert job.stage == "verify"
