from __future__ import annotations

from typing import Any


def run_import_once(repository: Any, pipeline: Any, worker_id: str) -> bool:
    job = repository.claim_next(worker_id)
    if job is None:
        return False
    try:
        pipeline.process(job)
    except Exception as exc:
        repository.mark_failed(job.id, error=str(exc))
    return True
